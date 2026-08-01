"""
multiagent/agents/verifier.py
------------------------------
Verifier agent: fifth and final agent in the multi-agent pipeline.

Gives a per-threat verdict on whether the generated code correctly implements
every mitigation from the original threat model. All four checks run
independently from the Code Reviewer.

  1. Bandit via MCP: static analysis (independent run, separate state field)
  2. Sandbox via MCP: executes the code, verifies it runs without errors
  3. RAG retrieval: re-queries CWE corpus independently to anchor verdicts
  4. GPT-4o synthesis: per-threat PASS/FAIL verdict + overall assessment

Key constraint: bandit_findings_verify is stored separately from
bandit_findings_review. These must never be merged: the Verifier is a
genuine second check, not a repeat of the Code Reviewer's run.

Run standalone:
    python -m multiagent.agents.verifier --test
"""

import asyncio
import json
import sys

from langfuse import observe, propagate_attributes

from config import MODEL, TEMPERATURE, client
from mcp_client import call_tool, get_client
from multiagent.state import (
    AgentState,
    ExecutionResult,
    ThreatCheckResult,
    ThreatEntry,
    VerificationResult,
)
from rag.retriever import format_for_prompt, retrieve


# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a security verifier in a multi-agent pipeline. Your job is to give an
independent verdict on whether the generated code correctly implements every
mitigation from the original threat model.

You are the last check before the code reaches the human participant. Be strict.
Partial implementations and ambiguous mitigations are a FAIL.

You will receive:
  - The generated code
  - The threat model with required mitigations
  - Independent Bandit static analysis findings
  - Independent CWE context from the MITRE corpus
  - Sandbox execution result

For each threat, decide:
  passed : true only if the mitigation is fully and correctly implemented
  notes  : one or two sentences. Cite the specific line or pattern you observed.

overall_pass is true ONLY if ALL threats passed AND execution passed (exit_code 0).

GOOD notes (passed):
"Parameterised query with ? placeholder on line 8. No string concatenation in SQL."

GOOD notes (failed):
"hashlib.md5() on line 14. CWE-916 requires bcrypt for password hashing. Not used."

BAD notes:
"The code looks secure." / "Mitigation appears to be implemented."

Respond with valid JSON only. No markdown, no extra keys:
{
  "threats_checked": [
    {
      "cwe_id": "CWE-89",
      "passed": true,
      "notes":  "Specific observation referencing the code."
    }
  ],
  "overall_pass": true,
  "notes": "One or two sentence overall verdict."
}"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_bandit(bandit_result: dict) -> str:
    if bandit_result.get("error"):
        return f"=== Bandit ===\nError: {bandit_result['error']}"
    findings = bandit_result.get("findings", [])
    summary  = bandit_result.get("summary", {})
    if not findings:
        return "=== Bandit ===\nNo issues found."
    lines = [
        f"=== Bandit: {summary.get('total', len(findings))} issue(s) "
        f"[HIGH: {summary.get('high', 0)}, MEDIUM: {summary.get('medium', 0)}] ===\n"
    ]
    for f in findings:
        lines.append(
            f"[Line {f.get('line_number', '?')}] {f.get('test_id', '')} - "
            f"{f.get('description', '')}\n"
            f"  Severity: {f.get('severity', '?')} | CWE: {f.get('cwe_id') or 'N/A'}"
        )
    return "\n\n".join(lines)


def _format_threats(threats: list[ThreatEntry]) -> str:
    if not threats:
        return "No threat model available."
    blocks = []
    for t in threats:
        blocks.append(
            f"[{t['cwe_id']}: {t['name']} ({t['severity']})\n"
            f"  Required mitigation: {t['mitigation']}"
        )
    return "\n\n".join(blocks)


def _format_execution(sandbox_result: dict) -> str:
    if sandbox_result.get("error"):
        return f"=== Sandbox ===\nError running sandbox: {sandbox_result['error']}"
    lines = [
        "=== Sandbox Execution ===",
        f"Passed    : {sandbox_result.get('passed', False)}",
        f"Timed out : {sandbox_result.get('timed_out', False)}",
        f"Exit code : {sandbox_result.get('exit_code', '?')}",
    ]
    if sandbox_result.get("stdout"):
        lines.append(f"Stdout    : {sandbox_result['stdout'][:300]}")
    if sandbox_result.get("stderr"):
        lines.append(f"Stderr    : {sandbox_result['stderr'][:300]}")
    return "\n".join(lines)


# ── Agent function ─────────────────────────────────────────────────────────────

@observe(name="verifier")
async def run_verifier(state: AgentState) -> dict:
    generated_code = state.get("generated_code") or ""
    threats        = state.get("threats") or []
    task           = state["task"]

    print("[Verifier] Starting independent verification...")

    try:
        mcp = get_client()

        # ── Step 1: Independent Bandit run ─────────────────────────────────────
        print("[Verifier] Running independent Bandit via MCP...")
        bandit_result       = await call_tool(mcp, "run_bandit", {"code": generated_code})
        bandit_findings_raw = bandit_result.get("findings", [])
        print(f"[Verifier] Bandit: {len(bandit_findings_raw)} finding(s)")

        # ── Step 2: Sandbox execution ──────────────────────────────────────────
        print("[Verifier] Running sandbox execution via MCP...")
        sandbox_result = await call_tool(mcp, "execute_code", {"code": generated_code})
        execution_result: ExecutionResult = {
            "passed":    sandbox_result.get("passed", False),
            "stdout":    sandbox_result.get("stdout", ""),
            "stderr":    sandbox_result.get("stderr", ""),
            "exit_code": sandbox_result.get("exit_code", -1),
        }
        print(
            f"[Verifier] Sandbox: passed={execution_result['passed']}, "
            f"exit_code={execution_result['exit_code']}"
        )

        # ── Step 3: Independent RAG retrieval ──────────────────────────────────
        print("[Verifier] Running independent RAG retrieval on CWE corpus...")
        rag_results = retrieve(task)
        cwe_context = format_for_prompt(rag_results)

        # ── Step 4: GPT-4o synthesis ───────────────────────────────────────────
        print("[Verifier] Running GPT-4o verification...")
        user_message = (
            f"CODE TO VERIFY:\n```python\n{generated_code}\n```\n\n"
            f"THREAT MODEL (verify each mitigation):\n{_format_threats(threats)}\n\n"
            f"INDEPENDENT BANDIT FINDINGS:\n{_format_bandit(bandit_result)}\n\n"
            f"INDEPENDENT CWE CONTEXT (MITRE corpus):\n{cwe_context}\n\n"
            f"SANDBOX EXECUTION:\n{_format_execution(sandbox_result)}"
        )

        session_id = f"{state['participant_id']}_{state.get('task_id', 'unknown')}"
        with propagate_attributes(
            session_id=session_id,
            user_id=state["participant_id"],
            tags=["multiagent", "verifier"],
            metadata={
                "bandit_findings_count": len(bandit_findings_raw),
                "sandbox_passed":        execution_result["passed"],
                "sandbox_exit_code":     execution_result["exit_code"],
            },
        ):
            response = client.chat.completions.create(
                model=MODEL,
                temperature=TEMPERATURE,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user",   "content": user_message},
                ],
                name="verifier",
            )

        raw = json.loads(response.choices[0].message.content)

        threats_checked: list[ThreatCheckResult] = [
            {
                "cwe_id": t.get("cwe_id", ""),
                "passed": bool(t.get("passed", False)),
                "notes":  t.get("notes", ""),
            }
            for t in raw.get("threats_checked", [])
        ]

        overall_pass = bool(raw.get("overall_pass", False))

        verification_result: VerificationResult = {
            "overall_pass":     overall_pass,
            "threats_checked":  threats_checked,
            "bandit_findings":  bandit_findings_raw,
            "execution_result": execution_result,
            "notes":            raw.get("notes", ""),
        }

        passed_count = sum(1 for t in threats_checked if t["passed"])
        print(
            f"[Verifier] {passed_count}/{len(threats_checked)} threats passed. "
            f"Overall: {'PASS' if overall_pass else 'FAIL'}"
        )

        return {
            "bandit_findings_verify": bandit_findings_raw,
            "verification_result":    verification_result,
            "final_code":             generated_code,
            "current_stage":          "complete",
            "error":                  None,
        }

    except Exception as e:
        error_msg = f"Verifier failed: {str(e)}"
        print(f"[Verifier] ERROR: {error_msg}")
        return {
            "bandit_findings_verify": None,
            "verification_result":    None,
            "final_code":             generated_code,
            "current_stage":          "error",
            "error":                  error_msg,
        }


# ── Standalone test mode ───────────────────────────────────────────────────────

async def _run_test() -> None:
    from multiagent.state import create_initial_state

    task  = "Write a Python function that checks a username and password against a SQLite database"
    state = create_initial_state("TEST", task)

    # Secure code: expect overall PASS
    state["generated_code"] = """\
import sqlite3
import bcrypt

def verify_user_credentials(username: str, password: str) -> bool:
    if not isinstance(username, str) or not isinstance(password, str):
        return False
    if not (0 < len(username) <= 128) or not (0 < len(password) <= 128):
        return False

    connection = None
    try:
        connection = sqlite3.connect('user_data.db')
        cursor = connection.cursor()
        cursor.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()

        if result is None:
            return False

        stored_password_hash = result[0]
        if bcrypt.checkpw(password.encode('utf-8'), stored_password_hash.encode('utf-8')):
            return True
        else:
            return False
    finally:
        if connection:
            connection.close()
"""

    state["threats"] = [
        {
            "cwe_id":      "CWE-89",
            "name":        "SQL Injection",
            "severity":    "Critical",
            "description": "Concatenating username into SQL allows authentication bypass.",
            "mitigation":  "Use sqlite3 parameterised queries with ? placeholder.",
        },
        {
            "cwe_id":      "CWE-20",
            "name":        "Improper Input Validation",
            "severity":    "Medium",
            "description": "Unvalidated inputs can cause unexpected behaviour.",
            "mitigation":  "Validate inputs are strings, non-empty, under 128 characters.",
        },
    ]

    print("Running Verifier test...\n")
    result = await run_verifier(state)

    print(f"\nStage         : {result['current_stage']}")
    print(f"Error         : {result['error']}")

    vr = result.get("verification_result")
    if vr:
        print(f"Overall pass  : {vr['overall_pass']}")
        print(f"Notes         : {vr['notes']}")
        print(f"Bandit (indep): {len(result.get('bandit_findings_verify') or [])} finding(s)")
        print(
            f"Sandbox       : passed={vr['execution_result']['passed']}, "
            f"exit_code={vr['execution_result']['exit_code']}"
        )
        print(f"\n--- THREAT VERDICTS ({len(vr['threats_checked'])}) ---")
        for t in vr["threats_checked"]:
            verdict = "PASS" if t["passed"] else "FAIL"
            print(f"\n  [{verdict}] {t['cwe_id']}")
            print(f"  {t['notes']}")


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        print("Run with --test to test the Verifier agent standalone.")