"""
multiagent/graph.py
-------------------
LangGraph pipeline wiring all five agents plus a finalise node.

Flow (linear):
    Planner -> Threat Modeller -> Code Generator -> Code Reviewer -> Verifier -> Finalise

Human-in-the-loop: the graph pauses after each of the first four agents so the
interface can show the output to the participant and collect their decision
(approve / revise / override). After the code_reviewer decision the Verifier
and finalise nodes run automatically with no further interrupts.

Usage
-----
    from multiagent.graph import graph, start_session, resume_session, get_current_state

    # Start -- runs Planner, then pauses
    config = await start_session("P01", "Write a login function", "T1", 2)

    # Inspect Planner output
    state = get_current_state(config)

    # Human approves plan -- runs Threat Modeller, then pauses
    await resume_session(config, {"plan_decision": decision})

    # ... repeat for threats_decision, code_decision ...

    # Human approves review -- Verifier + finalise run automatically
    await resume_session(config, {"review_decision": decision})
    state = get_current_state(config)
    # state["current_stage"] == "complete"
"""

import datetime
import json
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from multiagent.agents.code_generator import run_code_generator
from multiagent.agents.code_reviewer import run_code_reviewer
from multiagent.agents.planner import run_planner
from multiagent.agents.threat_modeller import run_threat_modeller
from multiagent.agents.verifier import run_verifier
from multiagent.state import AgentState, create_initial_state, to_log_entry
from evaluation.langfuse_eval import run_all_evals
from config import langfuse as _langfuse

LOG_PATH = Path(__file__).parent.parent / "logs" / "multiagent_sessions.jsonl"


# -- Finalise node --------------------------------------------------------------

async def _finalise(state: AgentState) -> dict:
    """Compute session duration, run evals, build JSONL log record, write to disk."""
    session_end = datetime.datetime.now(datetime.timezone.utc).isoformat()

    start    = datetime.datetime.fromisoformat(state["session_start"])
    end      = datetime.datetime.fromisoformat(session_end)
    duration = (end - start).total_seconds()

    # Run LLM-as-judge evaluations before writing the log so scores are included.
    try:
        eval_results = run_all_evals(state)
    except Exception as exc:
        print(f"[Graph] Eval failed (non-fatal): {exc}")
        eval_results = {"error": str(exc)}

    log_entry = to_log_entry(state)
    log_entry["session_end"]      = session_end
    log_entry["duration_seconds"] = round(duration, 3)

    # Attach eval scores under multi_agent_detail so they travel with the session.
    if "multi_agent_detail" not in log_entry:
        log_entry["multi_agent_detail"] = {}
    log_entry["multi_agent_detail"]["eval"] = eval_results

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    # Flush Langfuse buffer so all traces/scores are sent before the response
    # is returned to the frontend. Important in short-lived request contexts.
    if _langfuse:
        try:
            _langfuse.flush()
        except Exception:
            pass

    print(f"[Graph] Session complete. Duration: {duration:.1f}s -- logged to {LOG_PATH}")

    return {
        "session_end":      session_end,
        "duration_seconds": round(duration, 3),
        "log_entry":        log_entry,
        "current_stage":    "complete",
    }


# -- Build and compile graph ----------------------------------------------------

def _build() -> StateGraph:
    builder = StateGraph(AgentState)

    builder.add_node("planner",         run_planner)
    builder.add_node("threat_modeller", run_threat_modeller)
    builder.add_node("code_generator",  run_code_generator)
    builder.add_node("code_reviewer",   run_code_reviewer)
    builder.add_node("verifier",        run_verifier)
    builder.add_node("finalise",        _finalise)

    builder.set_entry_point("planner")
    builder.add_edge("planner",         "threat_modeller")
    builder.add_edge("threat_modeller", "code_generator")
    builder.add_edge("code_generator",  "code_reviewer")
    builder.add_edge("code_reviewer",   "verifier")
    builder.add_edge("verifier",        "finalise")
    builder.add_edge("finalise",        END)

    return builder


_checkpointer = MemorySaver()

graph = _build().compile(
    checkpointer=_checkpointer,
    interrupt_after=["planner", "threat_modeller", "code_generator", "code_reviewer"],
)


# -- Public helpers -------------------------------------------------------------

def _make_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


async def start_session(
    participant_id: str,
    task: str,
    task_id: str,
    task_order: int,
    thread_id: str | None = None,
) -> dict:
    """
    Initialise and start a new pipeline session.

    Runs the Planner, then pauses for human review.
    Returns the config dict required by all subsequent calls.

    Args:
        participant_id: e.g. "P01"
        task:           the coding task as submitted
        task_id:        e.g. "T1" -- which of the four tasks this is
        task_order:     1-4 -- the position in the participant's randomised sequence
        thread_id:      optional -- auto-generated from participant_id + timestamp
    """
    if thread_id is None:
        ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S")
        thread_id = f"{participant_id}_{ts}"

    initial_state = create_initial_state(participant_id, task, task_id, task_order)
    config = _make_config(thread_id)

    await graph.ainvoke(initial_state, config=config)
    return config


async def resume_session(config: dict, state_update: dict) -> None:
    """
    Apply a human decision to state then resume the graph.

    Call once for each stage the participant reviews:

        await resume_session(config, {"plan_decision":    decision})
        await resume_session(config, {"threats_decision": decision})
        await resume_session(config, {"code_decision":    decision})
        await resume_session(config, {"review_decision":  decision})

    After the final review_decision, the Verifier + finalise run automatically
    and the session reaches current_stage == "complete".
    """
    graph.update_state(config, state_update)
    await graph.ainvoke(None, config=config)


def get_current_state(config: dict) -> AgentState:
    """Return the latest state snapshot for a thread."""
    return graph.get_state(config).values


# -- Standalone test -----------------------------------------------------------

async def _run_test() -> None:
    from multiagent.agents.code_generator import finalize_code

    task = (
        "Write a Python function that takes a username and password as inputs, "
        "checks them against credentials stored in a SQLite database, and returns "
        "True if the login is successful or False if it is not."
    )

    # Sample code the simulated participant submits. Uses parameterised queries
    # and bcrypt so the Code Reviewer and Verifier have something meaningful to
    # analyse.
    _SAMPLE_CODE = """\
import sqlite3
import bcrypt

def check_credentials(username: str, password: str) -> bool:
    if not username or not password:
        return False
    if len(username) > 128 or len(password) > 128:
        return False
    conn = sqlite3.connect("users.db")
    try:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT password_hash FROM users WHERE username = ?",
            (username,),
        )
        row = cursor.fetchone()
        if row is None:
            return False
        return bcrypt.checkpw(password.encode(), row[0].encode())
    finally:
        conn.close()
"""

    def _approve(stage: str) -> dict:
        return {
            "action": "approve",
            "revised_content": None,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }

    print("=" * 60)
    print("GRAPH END-TO-END TEST  (HITL flow)")
    print("Task:", task[:80] + "...")
    print("=" * 60)

    # 1. Start -- runs Planner, then pauses
    print("\n[1/5] Running Planner...")
    config = await start_session("TEST", task, "T1", 1)
    state = get_current_state(config)
    plan = state.get("plan") or {}
    print(f"  Stage     : {state.get('current_stage')}")
    print(f"  Steps     : {len(plan.get('steps', []))}")
    print(f"  Sec reqs  : {len(plan.get('security_requirements', []))}")

    # 2. Approve plan -- runs Threat Modeller, then pauses
    print("\n[2/5] Approving plan. Running Threat Modeller...")
    await resume_session(config, {"plan_decision": _approve("plan")})
    state = get_current_state(config)
    threats = state.get("threats") or []
    print(f"  Stage     : {state.get('current_stage')}")
    print(f"  Threats   : {len(threats)}")
    for t in threats:
        print(f"    {t['cwe_id']} [{t['severity']}] {t['name']}")

    # 3. Approve threats -- runs Code Generator node (HITL init), then pauses.
    #    The node sets current_stage="coding_in_progress" and does NOT generate
    #    code. The graph waits for the participant to write and submit code.
    print("\n[3/5] Approving threats. Running Code Generator (HITL init)...")
    await resume_session(config, {"threats_decision": _approve("threats")})
    state = get_current_state(config)
    print(f"  Stage     : {state.get('current_stage')}  (expected: coding_in_progress)")
    assert state.get("current_stage") == "coding_in_progress", (
        f"Expected coding_in_progress but got: {state.get('current_stage')}"
    )
    assert state.get("generated_code") is None, (
        "generated_code should be None: participant has not submitted yet"
    )

    # 4. Simulate participant writing and submitting code.
    #    In production the frontend drives get_hint / finalize_code.
    #    Here we call finalize_code directly with sample code and HITL metrics,
    #    then resume the graph with those state updates.
    #    This triggers the Code Reviewer node.
    print("\n[4/5] Simulating participant code submission. Running Code Reviewer...")
    annotations = {
        "what_does_code_do": (
            "Checks username and password against a SQLite DB using "
            "parameterised queries and bcrypt hash comparison."
        ),
        "threats_addressed": ["CWE-89", "CWE-916", "CWE-307"],
        "submitted_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    finalize_updates = finalize_code(
        state,
        user_code=_SAMPLE_CODE,
        annotations=annotations,
        confidence_rating=4,
        hints_requested=[],
        time_in_coding_seconds=120.0,
    )
    await resume_session(config, finalize_updates)
    state = get_current_state(config)
    findings = state.get("review_findings") or []
    bandit   = state.get("bandit_findings_review") or []
    code     = state.get("generated_code") or ""
    print(f"  Stage       : {state.get('current_stage')}")
    print(f"  Code lines  : {len(code.splitlines())}")
    print(f"  Bandit hits : {len(bandit)}")
    print(f"  LLM findings: {len(findings)}")

    # 5. Approve review -- runs Verifier + finalise (no interrupt after this)
    print("\n[5/5] Approving review. Running Verifier + Finalise...")
    await resume_session(config, {"review_decision": _approve("review")})
    state = get_current_state(config)

    vr = state.get("verification_result") or {}
    print(f"\n  Stage        : {state.get('current_stage')}")
    print(f"  Overall PASS : {vr.get('overall_pass')}")
    print(f"  Duration     : {state.get('duration_seconds')}s")

    threats_checked = vr.get("threats_checked") or []
    print(f"\n  --- THREAT VERDICTS ({len(threats_checked)}) ---")
    for t in threats_checked:
        verdict = "PASS" if t["passed"] else "FAIL"
        print(f"  [{verdict}] {t['cwe_id']}: {t['notes']}")

    print(f"\n  Log entry written: {state.get('log_entry') is not None}")
    print("\n" + "=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    import asyncio
    import sys

    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        print("Run with --test to execute the full pipeline end-to-end.")