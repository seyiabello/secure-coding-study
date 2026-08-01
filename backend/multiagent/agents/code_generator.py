"""
multiagent/agents/code_generator.py
-------------------------------------
Code Generator agent: third stage of the multi-agent pipeline.

HITL REDESIGN: The Code Generator is a coding mentor. The participant writes
the code themselves. The agent provides step-scoped, escalating help via a
per-step hint ladder, plus two code-reading endpoints:

  Per-step hint ladder (four levels, per plan step):
    "direction" - plain English: what to do for this step and why
    "pseudocode" - comment-only skeleton scoped to this step
    "partial" - partial implementation with security TODOs for this step
    "full" - complete implementation (boilerplate steps only)

  Each step's maximum level is capped by the step classifier:
    - Security-critical steps (e.g. parameterised query, bcrypt): "direction" only
    - Logic steps: up to "partial"
    - Boilerplate (imports, DB open/close): up to "full"

  Code-reading endpoints:
    get_next_hint(state, code_so_far)
        Reads the participant's current code, identifies which steps are done /
        missing / wrong, and returns an adaptive next-step suggestion.

    get_security_hint(state, code_so_far)
        Reads the current code and flags the single most important security
        issue or missing mitigation. Always whole-code, security-focused.

Public API:
  get_step_hint(state, step_index, level) - request a per-step hint
  get_next_hint(state, code_so_far) - adaptive "what should I do next?"
  get_security_hint(state, code) - real-time security issue detector
  finalize_code(state, user_code, ...) - submit final code and HITL metrics
  run_code_generator(state) - LangGraph node (initialises stage)
"""

import asyncio
import datetime
import json
import sys
from typing import Optional

from config import MODEL, TEMPERATURE, client
from multiagent.state import (
    AgentState,
    CodingAnnotations,
    HintRecord,
    HitlCodingMetrics,
    PlannerOutput,
    ThreatEntry,
)


# =============================================================================
# Context helpers
# =============================================================================

def _format_plan(plan: PlannerOutput) -> str:
    steps = "\n".join(f"  {i + 1}. {s}" for i, s in enumerate(plan["steps"]))
    reqs = "\n".join(f"  - {r}" for r in plan["security_requirements"])
    return (
        f"SCOPE: {plan['scope']}\n\n"
        f"IMPLEMENTATION STEPS:\n{steps}\n\n"
        f"SECURITY REQUIREMENTS:\n{reqs}"
    )


def _format_threats(threats: list[ThreatEntry]) -> str:
    blocks = []
    for t in threats:
        blocks.append(
            f"[{t['cwe_id']}: {t['name']} ({t['severity']})\n"
            f"  What: {t['description']}\n"
            f"  Mitigation: {t['mitigation']}"
        )
    return "\n\n".join(blocks)


def _build_context(state: AgentState) -> str:
    task = state["task"]
    plan = state.get("plan")
    threats = state.get("threats") or []
    plan_text = _format_plan(plan) if plan else "No plan available."
    threats_text = _format_threats(threats) if threats else "No threats identified."
    return (
        f"TASK:\n{task}\n\n"
        f"PLAN:\n{plan_text}\n\n"
        f"THREAT MODEL:\n{threats_text}"
    )


def _build_step_context(state: AgentState, step_index: int) -> str:
    """Build a focused context for a single plan step."""
    task = state["task"]
    plan = state.get("plan") or {}
    threats = state.get("threats") or []
    steps = plan.get("steps", [])

    step_text = steps[step_index] if step_index < len(steps) else "Unknown step"

    # Steps before this one, for context
    prior_steps = "\n".join(
        f"  {i + 1}. {s} [done before this step]"
        for i, s in enumerate(steps[:step_index])
    ) or "  (this is the first step)"

    # Steps after, so the hint doesn't overlap
    later_steps = "\n".join(
        f"  {i + step_index + 2}. {s}"
        for i, s in enumerate(steps[step_index + 1:])
    ) or "  (this is the last step)"

    threats_text = _format_threats(threats) if threats else "No threats identified."

    return (
        f"TASK: {task}\n\n"
        f"CURRENT STEP (step {step_index + 1}): {step_text}\n\n"
        f"PRIOR STEPS (already implemented):\n{prior_steps}\n\n"
        f"LATER STEPS (not yet, do not hint at these):\n{later_steps}\n\n"
        f"THREAT MODEL:\n{threats_text}"
    )


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


# =============================================================================
# Per-step hint prompts
# =============================================================================

_STEP_HINT_PROMPTS: dict[str, str] = {

    "direction": """\
You are a coding mentor helping a developer write secure Python code one step at a time.

The developer is working on ONE specific step. Give them direction for THIS step only.
Do not hint at steps that come before or after.

Your response for this step:
- State in plain English what this step requires the developer to implement
- Explain WHY this step is necessary and how it fits into the overall function
- If this step touches security-critical logic, state the relevant CWE in one sentence
  and what to be careful about, but do NOT describe how to implement the security fix

Rules:
- NO code. NO pseudocode. Plain English only.
- Scope strictly to this one step. Ignore what comes after.
- 3 to 5 sentences for the direction. 1 sentence for the security note.

Respond with valid JSON only:
{
  "content": "<plain English direction for this step>",
  "security_note": "<one sentence security reminder, or empty string if not applicable>"
}""",

    "pseudocode": """\
You are a coding mentor helping a developer write secure Python code one step at a time.

The developer needs a pseudocode skeleton for ONE specific step. Scope to THIS step only.

Generate a Python comment-only pseudocode skeleton for this step:
- Use only # comment lines. Zero executable code.
- Cover only what this step needs to do. Do not bleed into adjacent steps.
- If the step has security-critical work, name the CWE but do NOT describe the implementation
- Include a "security: [CWE-XX]" sub-comment for any security-sensitive action

Good example (for a "query the database" step):
# 3. Query the database for the given username
#    - Use the cursor to run the SELECT query
#    - security: [CWE-89] use parameterised form. Do NOT build the query string manually.
#    - Fetch one row

Rules:
- Comment lines only. No executable Python.
- Strictly scoped to this step. No code for other steps.
- Maximum 6 to 8 comment lines. Skeleton only, not a tutorial.

Respond with valid JSON only:
{
  "content": "<pseudocode comments as a single string, \\n for newlines>",
  "security_note": "<one sentence on the most critical security aspect of this step, or empty string>"
}""",

    "partial": """\
You are a coding mentor helping a developer write secure Python code one step at a time.

The developer needs partial implementation for ONE specific step. This step is NOT
security-critical, but it may still have security-adjacent elements to be careful about.

Generate partial Python code for this step only:
- INCLUDE: structural scaffolding, safe operations, variable assignments, type checks
  that are clearly not the security-critical part
- OMIT with # TODO markers: any logic that touches security-sensitive areas,
  even if this step is "partial". The developer must write those parts.
- Each TODO must be a single line stating what is needed and referencing the CWE if applicable

TODO format:
    # TODO [CWE-XX]: brief description of what the developer must implement here

Scope strictly to this step. Do not generate code for other steps.
Keep the total response to 8 to 12 lines of code maximum.

Respond with valid JSON only:
{
  "content": "<partial Python code for this step as a single string, \\n for newlines>",
  "security_note": "<one sentence on what the developer must implement in the TODO, or empty string>"
}""",

    "full": """\
You are a coding mentor helping a developer write secure Python code one step at a time.

The developer needs the full implementation for ONE specific step. This is a boilerplate
or setup step with no security-critical decisions. The security work happens elsewhere.

Generate complete Python code for this step only:
- Complete and correct for just this step
- Add a brief inline comment if the reason for something is non-obvious
- Do NOT generate code for steps before or after this one

This step has been classified as boilerplate (e.g. opening a connection, declaring
variables, importing a library). The security decisions belong to other steps.

Respond with valid JSON only:
{
  "content": "<complete Python code for this step only, \\n for newlines>",
  "security_note": "<reminder about where the security work actually happens, one sentence>"
}""",
}

_LEVEL_DEPTH = {"direction": 1, "pseudocode": 2, "partial": 3, "full": 4, "adaptive": 0, "security": 0}


# =============================================================================
# Adaptive next-hint prompt
# =============================================================================

_NEXT_HINT_PROMPT = """\
You are a coding mentor watching a developer implement a secure coding task.

You will receive:
  - The coding task
  - The full plan (ordered steps the developer is following)
  - The threat model (security issues they must address)
  - The developer's current partial code

Your job:
1. Identify which plan steps appear to be complete in the code
2. Identify the single most useful next action for the developer:
   a. The next step they should implement (if they're working in order)
   b. A correction to something they've started but done incorrectly
   c. A missing security measure they've skipped

Rules:
- ONE focused suggestion. Not a comprehensive review.
- Reference the specific step number from the plan.
- If you spot a security issue, name the CWE and explain the concern concisely.
  Do NOT provide the fix. Describe what needs attention.
- If the code looks complete for all steps, say so and prompt them to review
  the threat model before submitting.
- If the code is too short to evaluate meaningfully, say what the next step is.

Respond with valid JSON only:
{
  "next_step_index": <0-indexed step number being suggested, or null if complete>,
  "status": "<one of: missing | partial | issue | complete>",
  "content": "<2-4 sentences describing what to do next or what needs attention>",
  "security_note": "<one sentence if a specific CWE is relevant, else empty string>"
}"""


# =============================================================================
# Security hint prompt (real-time, whole-code)
# =============================================================================

_SECURITY_HINT_PROMPT = """\
You are a real-time security reviewer watching a developer write Python code.

You will receive the task, the threat model, and the developer's current partial code.

Your job:
1. Identify the single most important security issue in the current code:
   something that is wrong, missing, or about to go wrong given the threat model.
2. If the code is clean so far, identify the most critical security measure
   the developer still needs to implement.

Rules:
- ONE issue only. The most pressing one.
- One sentence naming the issue. One sentence suggesting what to check or do.
- Do NOT rewrite the code. Do NOT give a full solution.
- If the code is too short or empty to evaluate, return has_issue: false.

Respond with valid JSON only:
{
  "has_issue": true,
  "issue": "<one sentence describing the security problem>",
  "suggestion": "<one sentence suggesting what to do>",
  "cwe_id": "<e.g. CWE-89, or null if unclear>"
}"""


# =============================================================================
# Public API
# =============================================================================

async def get_step_hint(state: AgentState, step_index: int, level: str) -> dict:
    """
    Returns a hint for a specific plan step at the requested level.

    The route handler is responsible for enforcing step_hint_caps: this
    function generates the hint regardless of cap. Cap enforcement happens
    before calling this function.

    Parameters
    ----------
    state : AgentState
        Current pipeline state. Reads: task, plan, threats.
    step_index : int
        0-indexed position of the step in plan.steps.
    level : str
        "direction" | "pseudocode" | "partial" | "full"

    Returns
    -------
    dict
        Keys: step_index, level, content, security_note, timestamp, error
    """
    if level not in _STEP_HINT_PROMPTS:
        return {
            "step_index":    step_index,
            "level":         level,
            "content":       "",
            "security_note": "",
            "timestamp":     _now(),
            "error":         f"Invalid hint level '{level}'.",
        }

    plan = state.get("plan") or {}
    steps = plan.get("steps", [])
    if step_index < 0 or step_index >= len(steps):
        return {
            "step_index":    step_index,
            "level":         level,
            "content":       "",
            "security_note": "",
            "timestamp":     _now(),
            "error":         f"Step index {step_index} out of range (plan has {len(steps)} steps).",
        }

    print(f"[Code Generator] Step {step_index + 1} hint '{level}' requested")

    context = _build_step_context(state, step_index)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=TEMPERATURE,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _STEP_HINT_PROMPTS[level]},
                {"role": "user",   "content": context},
            ],
        )

        data = json.loads(response.choices[0].message.content)

        return {
            "step_index":    step_index,
            "level":         level,
            "content":       data.get("content", "").strip(),
            "security_note": data.get("security_note", "").strip(),
            "timestamp":     _now(),
            "error":         None,
        }

    except Exception as exc:
        return {
            "step_index":    step_index,
            "level":         level,
            "content":       "",
            "security_note": "",
            "timestamp":     _now(),
            "error":         f"Hint generation failed: {exc}",
        }


async def get_next_hint(state: AgentState, code_so_far: str) -> dict:
    """
    Adaptive hint: reads the participant's current code and suggests what to do next.

    Identifies which plan steps are done/missing/wrong and returns a focused,
    targeted suggestion: not a full review. Replaces the old whole-task direction hint.

    Parameters
    ----------
    state : AgentState
        Current pipeline state. Reads: task, plan, threats.
    code_so_far : str
        The participant's current (partial) code from the editor.

    Returns
    -------
    dict
        Keys: next_step_index, status, content, security_note, timestamp, error
    """
    if len(code_so_far.strip()) < 20:
        return {
            "next_step_index": 0,
            "status":          "missing",
            "content":         "Start by reading the plan steps in the sidebar. Begin with step 1.",
            "security_note":   "",
            "timestamp":       _now(),
            "error":           None,
        }

    context = _build_context(state)
    user_message = f"{context}\n\nDEVELOPER'S CURRENT CODE:\n{code_so_far}"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _NEXT_HINT_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )

        data = json.loads(response.choices[0].message.content)

        return {
            "next_step_index": data.get("next_step_index"),
            "status":          data.get("status", "missing"),
            "content":         data.get("content", "").strip(),
            "security_note":   data.get("security_note", "").strip(),
            "timestamp":       _now(),
            "error":           None,
        }

    except Exception as exc:
        return {
            "next_step_index": None,
            "status":          "missing",
            "content":         "",
            "security_note":   "",
            "timestamp":       _now(),
            "error":           f"Adaptive hint failed: {exc}",
        }


async def get_security_hint(state: AgentState, code_so_far: str) -> dict:
    """
    Analyses the participant's current code and returns one security-focused hint.

    Whole-code pass: not scoped to a step. Flags the single most important
    security issue or missing mitigation in what has been written so far.

    Parameters
    ----------
    state : AgentState
        Current pipeline state. Reads: task, threats.
    code_so_far : str
        The participant's current (partial) code from the editor.
    """
    if len(code_so_far.strip()) < 30:
        return {
            "has_issue":  False,
            "issue":      "",
            "suggestion": "",
            "cwe_id":     None,
            "timestamp":  _now(),
            "error":      None,
        }

    threats = state.get("threats") or []
    threats_text = _format_threats(threats) if threats else "No threats identified."

    user_message = (
        f"TASK: {state['task']}\n\n"
        f"THREAT MODEL:\n{threats_text}\n\n"
        f"DEVELOPER'S CURRENT CODE:\n{code_so_far}"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SECURITY_HINT_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )

        data = json.loads(response.choices[0].message.content)

        return {
            "has_issue":  bool(data.get("has_issue", False)),
            "issue":      data.get("issue", "").strip(),
            "suggestion": data.get("suggestion", "").strip(),
            "cwe_id":     data.get("cwe_id") or None,
            "timestamp":  _now(),
            "error":      None,
        }

    except Exception as exc:
        return {
            "has_issue":  False,
            "issue":      "",
            "suggestion": "",
            "cwe_id":     None,
            "timestamp":  _now(),
            "error":      f"Security hint failed: {exc}",
        }


def finalize_code(
    state: AgentState,
    user_code: str,
    annotations: CodingAnnotations,
    confidence_rating: int,
    hints_requested: list[HintRecord],
    time_in_coding_seconds: float,
) -> dict:
    """
    Stores the participant's final code and all HITL metrics.

    hint_depth_reached is computed as the deepest level used across all steps:
    direction=1, pseudocode=2, partial=3, full=4. Adaptive and security hints
    do not contribute to the depth score.
    """
    depth_reached = max(
        (_LEVEL_DEPTH.get(h.get("level", ""), 0) for h in hints_requested),
        default=0,
    )

    hitl_metrics: HitlCodingMetrics = {
        "hint_depth_reached":     depth_reached,
        "hints_requested":        hints_requested,
        "time_in_coding_seconds": round(time_in_coding_seconds, 1),
        "confidence_rating":      max(1, min(5, confidence_rating)),
        "annotations":            annotations,
    }

    print(
        f"[Code Generator] Code finalised: "
        f"hint depth reached: {depth_reached}, "
        f"confidence: {confidence_rating}/5, "
        f"time: {time_in_coding_seconds:.0f}s"
    )

    return {
        "generated_code":  user_code,
        "code_explanation": None,
        "hitl_coding":     hitl_metrics,
        "current_stage":   "code_review",
        "error":           None,
    }


# =============================================================================
# LangGraph node
# =============================================================================

async def run_code_generator(state: AgentState) -> dict:
    """
    LangGraph node for the code generation stage.

    Initialises the coding stage and sets current_stage to "coding_in_progress"
    so the graph knows to pause and wait for the human. The frontend drives
    get_step_hint / get_next_hint / get_security_hint / finalize_code.
    """
    print("[Code Generator] Coding stage initialised: waiting for participant.")

    return {
        "generated_code":        None,
        "code_explanation":      None,
        "hitl_coding":           None,
        "pre_review_prediction": None,
        "prediction_accuracy":   None,
        "current_stage":         "coding_in_progress",
        "error":                 None,
    }


# =============================================================================
# Standalone test
# =============================================================================

async def _run_test():
    from multiagent.state import create_initial_state

    state = create_initial_state(
        "TEST",
        "Write a Python function that checks a username and password against a SQLite database",
    )

    state["plan"] = {
        "steps": [
            "Validate that username and password are non-empty strings under 128 characters",
            "Open a connection to the SQLite database",
            "Query the stored password hash using a parameterised query",
            "If no user found, return False without revealing which field failed",
            "Verify the submitted password against the stored hash using bcrypt",
            "Return True if the hash matches, False otherwise",
            "Close the database connection in a finally block",
        ],
        "scope": (
            "A single Python function that verifies a username and password against "
            "a SQLite database. No sessions, no registration, no password reset."
        ),
        "security_requirements": [
            "Use parameterised queries to prevent SQL injection",
            "Hash passwords with bcrypt: never compare plaintext",
            "Return a generic failure response: do not reveal which field was wrong",
            "Validate input types and lengths before touching the database",
        ],
    }

    state["threats"] = [
        {
            "cwe_id": "CWE-89", "name": "SQL Injection", "severity": "Critical",
            "description": "Concatenating username into the SQL query allows injection.",
            "mitigation": "Use sqlite3 parameterised queries with the ? placeholder.",
        },
        {
            "cwe_id": "CWE-20", "name": "Improper Input Validation", "severity": "Medium",
            "description": "Arbitrary-length inputs can cause unexpected behaviour.",
            "mitigation": "Validate username and password are strings under 128 chars.",
        },
        {
            "cwe_id": "CWE-916", "name": "Weak Password Hashing", "severity": "High",
            "description": "Comparing passwords as plaintext exposes credentials.",
            "mitigation": "Use bcrypt.checkpw() to verify passwords against stored hashes.",
        },
    ]

    sep = "=" * 60

    # Test step hints at each level for a security-critical step (step 2: parameterised query)
    print(f"\n{sep}\nSTEP 2 (parameterised query) - DIRECTION\n{sep}")
    r = await get_step_hint(state, 2, "direction")
    print(r["content"])
    if r["security_note"]:
        print(f"\n[Security] {r['security_note']}")

    print(f"\n{sep}\nSTEP 2 (parameterised query) - PSEUDOCODE\n{sep}")
    r = await get_step_hint(state, 2, "pseudocode")
    print(r["content"])

    # Test step hints for a boilerplate step (step 1: open DB connection)
    print(f"\n{sep}\nSTEP 1 (open DB connection) - FULL\n{sep}")
    r = await get_step_hint(state, 1, "full")
    print(r["content"])

    # Test adaptive next hint
    print(f"\n{sep}\nADAPTIVE: NEXT HINT (partial code)\n{sep}")
    partial_code = (
        "import sqlite3\nimport bcrypt\n\n"
        "def verify_credentials(username: str, password: str) -> bool:\n"
        "    conn = sqlite3.connect('users.db')\n"
        "    cursor = conn.cursor()\n"
        '    query = f"SELECT * FROM users WHERE username = \'{username}\'"\n'
        "    cursor.execute(query)\n"
        "    row = cursor.fetchone()\n"
    )
    r = await get_next_hint(state, partial_code)
    print(f"Status: {r['status']}, Next step: {r['next_step_index']}")
    print(r["content"])
    if r["security_note"]:
        print(f"[Security] {r['security_note']}")

    # Test security hint
    print(f"\n{sep}\nSECURITY HINT (same partial code)\n{sep}")
    r = await get_security_hint(state, partial_code)
    print(f"Has issue: {r['has_issue']}, CWE: {r['cwe_id']}")
    print(r["issue"])
    print(r["suggestion"])


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        print("Run with --test to test all hint functions standalone.")
