"""
multiagent/agents/planner.py
----------------------------
Planner agent: first stage of the multi-agent pipeline.

Takes the participant's coding task and produces a structured implementation plan.

Output (stored in state["plan"]):
  steps                : ordered implementation tasks for the Code Generator
  scope                : one sentence on what the code should and should not do
  security_requirements: high-level security properties the code must satisfy

No RAG, no MCP. Direct GPT-4o call with JSON output.

This is the only agent in the pipeline that runs before the threat model.
Its security_requirements field is what forces the multi-agent system to think
about security explicitly before any code is written: something the baseline
never does.
"""

import asyncio
import json

from langfuse import observe, propagate_attributes

from config import MODEL, TEMPERATURE, client
from multiagent.state import AgentState, PlannerOutput

# ── System prompt ──────────────────────────────────────────────────────────────
#
# The Planner prompt is intentionally separate from the later security-heavy
# prompts. The Planner's job is to clarify scope and identify high-level
# security properties. The Threat Modeller does the deep security analysis.

SYSTEM_PROMPT = """\
You are a senior software engineering Planner. Your job is to analyse a coding \
task and produce a clear, structured implementation plan before any code is written.

You produce three outputs:

1. steps
   A list of 3 to 6 ordered implementation steps for the Code Generator to follow.
   Each step is a concrete action, not a vague intention.
   Good: "Hash the password with bcrypt before storing"
   Bad:  "Handle passwords securely"

2. scope
   Exactly one sentence describing what the code should do AND what it should not do.
   The "should not" part is important: it sets the boundary so the Code Generator
   does not add unnecessary features that introduce attack surface.
   Example: "Write a Python login function that checks username and password against
   a database; does not handle sessions, tokens, or account creation."

3. security_requirements
   A list of 3 to 5 security properties the final code must satisfy.
   These are high-level and task-specific, not generic advice.
   Good: "Passwords must be hashed with bcrypt, not stored in plain text"
   Bad:  "The code should be secure"
   These requirements will be passed to the Threat Modeller, Code Generator,
   Code Reviewer, and Verifier, so they must be clear and testable.

Respond with valid JSON only. No other text. Use this exact schema:
{
  "steps": ["step 1", "step 2", "..."],
  "scope": "one sentence describing what the code does and does not do",
  "security_requirements": ["requirement 1", "requirement 2", "..."]
}"""


# ── Agent function ─────────────────────────────────────────────────────────────

@observe(name="planner")
async def run_planner(state: AgentState) -> dict:
    """
    Planner agent node for the LangGraph graph.

    Reads the task from state, calls GPT-4o to produce a structured plan,
    and returns the state updates that LangGraph will merge back in.

    Parameters
    ----------
    state : AgentState
        The current pipeline state. Only state["task"] is read here.

    Returns
    -------
    dict
        State updates:
          plan           : PlannerOutput with steps, scope, security_requirements
          current_stage  : "threat_modelling" on success, "error" on failure
          error          : None on success, error message string on failure
    """
    task       = state["task"]
    session_id = f"{state['participant_id']}_{state.get('task_id', 'unknown')}"

    # Check whether this is a revision run (participant requested changes)
    prior_decision = state.get("plan_decision") or {}
    revision_notes = prior_decision.get("revised_content") or ""
    is_revision    = prior_decision.get("action") == "revise"

    if is_revision and revision_notes:
        print(f"[Planner] Revising plan per participant feedback...")
        user_message = (
            f"Coding task: {task}\n\n"
            f"The participant has reviewed the initial plan and requested revisions. "
            f"Please produce an updated plan that addresses this feedback:\n{revision_notes}"
        )
    else:
        print(f"[Planner] Planning task: {task[:80]}...")
        user_message = f"Coding task: {task}"

    try:
        with propagate_attributes(
            session_id=session_id,
            user_id=state["participant_id"],
            tags=["multiagent", "planner"],
        ):
            response = client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                name="planner",
            )

        raw = json.loads(response.choices[0].message.content)

        # Validate structure and apply safe defaults.
        # If GPT-4o omits a field (should not happen with this prompt), we
        # return empty values rather than crashing. The graph can continue
        # and the participant can fill gaps during the human-in-the-loop step.
        plan: PlannerOutput = {
            "steps":                 raw.get("steps", []),
            "scope":                 raw.get("scope", ""),
            "security_requirements": raw.get("security_requirements", []),
        }

        print(f"[Planner] Plan produced: {len(plan['steps'])} steps, "
              f"{len(plan['security_requirements'])} security requirements")

        return {
            "plan":          plan,
            "plan_decision": None,  # clear so conditional routing works after next interrupt
            "current_stage": "threat_modelling",
            "error":         None,
        }

    except Exception as e:
        # Return an error state so the graph can surface this to the participant
        # rather than crashing the entire pipeline.
        error_msg = f"Planner failed: {str(e)}"
        print(f"[Planner] ERROR: {error_msg}")
        return {
            "plan":          None,
            "plan_decision": None,
            "current_stage": "error",
            "error":         error_msg,
        }


# ── Standalone test mode ───────────────────────────────────────────────────────

async def _run_test() -> None:
    """
    Tests the Planner agent directly without the full LangGraph pipeline.

    Run with: python -m multiagent.agents.planner --test
    """
    from multiagent.state import create_initial_state

    task = (
        "Write a Python function that accepts a username and password, "
        "checks them against a SQLite database, and returns True if valid."
    )

    print(f"Task: {task}\n")
    state = create_initial_state("TEST", task)
    updates = await run_planner(state)

    print(f"\ncurrent_stage : {updates['current_stage']}")
    print(f"error         : {updates['error']}")

    if updates["plan"]:
        plan = updates["plan"]
        print(f"\nSCOPE\n  {plan['scope']}")
        print("\nSTEPS")
        for i, step in enumerate(plan["steps"], 1):
            print(f"  {i}. {step}")
        print("\nSECURITY REQUIREMENTS")
        for req in plan["security_requirements"]:
            print(f"  - {req}")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        print("Run with --test to test the Planner agent standalone.")
