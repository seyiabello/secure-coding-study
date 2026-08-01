"""
multiagent/agents/threat_modeller.py
-------------------------------------
Threat Modeller agent — second stage of the multi-agent pipeline.

Takes the task and the Planner's output, then produces a structured threat model
grounded in real security data from two sources:
  1. RAG  — top-3 CWE chunks from the MITRE CWE Top 25 corpus
  2. MCP  — recent CVEs from NIST NVD matching the task's primary threat

Output (stored in state["threats"] and state["rag_context"]):
  rag_context : the raw RAG retrieval results (stored for logging/transparency)
  threats     : list[ThreatEntry] — each threat has cwe_id, name, severity,
                task-specific description, and actionable mitigation

The Threat Modeller's mitigations are passed forward to the Code Generator,
Code Reviewer, and Verifier — so they must be concrete and implementable,
not generic advice.
"""

import asyncio
import json

from langfuse import observe, propagate_attributes

from config import MODEL, TEMPERATURE, client
from mcp_client import call_tool, get_client
from multiagent.state import AgentState, ThreatEntry
from rag.retriever import format_for_prompt, retrieve

# ── System prompt ──────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a security threat modeller. Your job is to identify the most important \
security threats for a specific coding task, grounded in the CWE and CVE data \
provided.

You will be given:
  - The coding task
  - A plan with scope and security requirements already identified
  - Relevant CWE entries from the MITRE Top 25 (your primary reference)
  - Recent CVEs from NIST NVD related to the primary threat

Produce a threat model with 3 to 5 threats. For each threat:

  cwe_id      : the official CWE identifier, e.g. "CWE-89"
  name        : the short CWE name, e.g. "SQL Injection"
  severity    : one of "Critical", "High", or "Medium"
  description : one or two sentences explaining how this specific threat applies
                to THIS task, not a generic CWE description. Be concrete.
                Example: "The login function builds a SQL query by concatenating
                the username string, allowing an attacker to inject SQL and
                bypass authentication."
  mitigation  : one or two sentences telling the Code Generator exactly what to
                do. This will be used as a direct instruction to the developer.
                Example: "Use parameterised queries (cursor.execute with ?
                placeholders). Never concatenate user input into SQL strings."

Rules:
  - Only include threats relevant to this task. Do not include generic threats
    that do not apply to the specific code being written.
  - Prioritise threats by severity: list Critical threats first.
  - Draw from the provided CWE and CVE data. Reference CWE IDs that appear in
    the context.
  - The description must be task-specific. The mitigation must be actionable.

Respond with valid JSON only. No other text. Use this exact schema:
{
  "threats": [
    {
      "cwe_id":      "CWE-XX",
      "name":        "Threat Name",
      "severity":    "Critical",
      "description": "How this threat applies to this specific task.",
      "mitigation":  "Exact instruction for the Code Generator."
    }
  ]
}"""


# ── Helper: format NVD results for the prompt ──────────────────────────────────

def _format_nvd_cves(nvd_result: dict) -> str:
    """
    Converts NVD search results into a readable string for the prompt.

    If NVD returned an error or no CVEs, returns a placeholder so the
    Threat Modeller can still run using only CWE context.
    """
    if nvd_result.get("error"):
        return f"=== NIST NVD ===\nNVD unavailable: {nvd_result['error']}"

    cves = nvd_result.get("cves", [])
    if not cves:
        return "=== NIST NVD ===\nNo matching CVEs found."

    lines = [
        f"=== Recent CVEs from NIST NVD "
        f"(keyword: '{nvd_result.get('keyword', '')}') ===\n"
    ]
    for cve in cves:
        cwe_list = ", ".join(cve["cwe_ids"]) if cve["cwe_ids"] else "N/A"
        lines.append(
            f"[{cve['cve_id']}] Severity: {cve['severity']} | "
            f"CVSS: {cve['cvss_score']} | Published: {cve['published']}\n"
            f"CWEs: {cwe_list}\n"
            f"{cve['description'][:250]}\n"
            f"Reference: {cve['nvd_url']}\n"
            f"{'-' * 50}"
        )
    return "\n".join(lines)


# ── Agent function ─────────────────────────────────────────────────────────────

@observe(name="threat_modeller")
async def run_threat_modeller(state: AgentState) -> dict:
    """
    Threat Modeller agent node for the LangGraph graph.

    Reads task and plan from state, enriches context with RAG and NVD data,
    and calls GPT-4o to produce a structured threat model.

    Parameters
    ----------
    state : AgentState
        Reads: task, plan (for scope and security_requirements)

    Returns
    -------
    dict
        State updates:
          rag_context    : raw RAG retrieval results (for logging)
          threats        : list[ThreatEntry] — the threat model
          current_stage  : "code_generation" on success, "error" on failure
          error          : None on success, error message on failure
    """
    task = state["task"]
    plan = state.get("plan") or {}

    print(f"[Threat Modeller] Analysing task: {task[:80]}...")

    try:
        # ── Step 1: RAG retrieval ──────────────────────────────────────────────
        # retrieve() runs the full advanced RAG pipeline:
        # query rewrite -> metadata filter -> vector search -> LLM re-rank -> top-3
        # Results contain CWE descriptions, mitigations, and examples from
        # the MITRE Top 25 corpus.
        print("[Threat Modeller] Running RAG retrieval on CWE corpus...")
        rag_results = retrieve(task)
        cwe_context = format_for_prompt(rag_results)

        # ── Step 2: NVD search ─────────────────────────────────────────────────
        # Use the top CWE's short name (e.g. "SQL Injection") as the NVD search
        # keyword. This gives focused CVE results without an extra GPT-4o call.
        print("[Threat Modeller] Querying NIST NVD for recent CVEs...")
        nvd_keyword = (
            rag_results[0]["metadata"]["short_name"]
            if rag_results
            else task[:50]
        )
        try:
            mcp = get_client()
            nvd_result = await asyncio.wait_for(
                call_tool(mcp, "search_nvd", {"keyword": nvd_keyword, "max_results": 3}),
                timeout=25.0,
            )
        except asyncio.TimeoutError:
            print("[Threat Modeller] NVD call timed out after 25 s — continuing with RAG only.")
            nvd_result = {
                "cves": [], "total_found": 0, "keyword": nvd_keyword,
                "error": "NVD search timed out — proceeding with CWE context only.",
            }
        except Exception as nvd_exc:
            print(f"[Threat Modeller] NVD call failed: {nvd_exc} — continuing with RAG only.")
            nvd_result = {
                "cves": [], "total_found": 0, "keyword": nvd_keyword,
                "error": f"NVD search failed: {nvd_exc}",
            }
        nvd_context = _format_nvd_cves(nvd_result)

        # ── Step 3: Build user message ─────────────────────────────────────────
        # Assemble all context: task, plan scope, security requirements,
        # CWE data from RAG, and CVE data from NVD.
        security_reqs = "\n".join(
            f"  - {r}" for r in plan.get("security_requirements", [])
        ) or "  None identified yet."

        user_message = (
            f"Coding task: {task}\n\n"
            f"Plan scope: {plan.get('scope', 'N/A')}\n\n"
            f"Security requirements already identified by the Planner:\n"
            f"{security_reqs}\n\n"
            f"{cwe_context}\n\n"
            f"{nvd_context}"
        )

        # ── Step 4: Generate threat model ──────────────────────────────────────
        # GPT-4o reads all the context and produces structured ThreatEntry dicts.
        print("[Threat Modeller] Generating threat model with GPT-4o...")
        session_id = f"{state['participant_id']}_{state.get('task_id', 'unknown')}"
        with propagate_attributes(
            session_id=session_id,
            user_id=state["participant_id"],
            tags=["multiagent", "threat_modeller"],
            metadata={
                "rag_chunks_retrieved": len(rag_results),
                "nvd_cves_retrieved":   len(nvd_result.get("cves", [])),
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
                name="threat_modeller",
            )

        raw = json.loads(response.choices[0].message.content)
        raw_threats = raw.get("threats", [])

        # Normalise each entry into the ThreatEntry TypedDict structure.
        threats: list[ThreatEntry] = [
            {
                "cwe_id":      t.get("cwe_id", ""),
                "name":        t.get("name", ""),
                "severity":    t.get("severity", ""),
                "description": t.get("description", ""),
                "mitigation":  t.get("mitigation", ""),
            }
            for t in raw_threats
        ]

        print(f"[Threat Modeller] {len(threats)} threats identified: "
              f"{[t['cwe_id'] for t in threats]}")

        return {
            "rag_context":   rag_results,
            "threats":       threats,
            "current_stage": "code_generation",
            "error":         None,
        }

    except Exception as e:
        error_msg = f"Threat Modeller failed: {str(e)}"
        print(f"[Threat Modeller] ERROR: {error_msg}")
        return {
            "rag_context":   None,
            "threats":       None,
            "current_stage": "error",
            "error":         error_msg,
        }


# ── Standalone test mode ───────────────────────────────────────────────────────

async def _run_test() -> None:
    """
    Tests the Threat Modeller directly without the full LangGraph pipeline.

    Run with: python -m multiagent.agents.threat_modeller --test

    Uses a pre-built plan so you can test the full RAG + NVD + GPT-4o flow
    without needing to run the Planner first.
    """
    from multiagent.state import PlannerOutput, create_initial_state

    task = (
        "Write a Python function that accepts a username and password, "
        "checks them against a SQLite database, and returns True if valid."
    )

    # Simulate the Planner's output so we can test this agent in isolation.
    plan: PlannerOutput = {
        "steps": [
            "Connect to the SQLite database.",
            "Retrieve the stored password hash for the given username.",
            "Hash the input password with bcrypt.",
            "Compare the hashes and return True if they match.",
        ],
        "scope": (
            "Write a Python login function that checks username and password "
            "against a SQLite database; does not handle sessions or registration."
        ),
        "security_requirements": [
            "Use parameterised queries to prevent SQL injection.",
            "Use bcrypt for password hashing, not MD5 or SHA1.",
            "Do not expose database error messages to the caller.",
        ],
    }

    state = create_initial_state("TEST", task)
    state["plan"] = plan

    print(f"Task: {task}\n")
    updates = await run_threat_modeller(state)

    print(f"\ncurrent_stage : {updates['current_stage']}")
    print(f"error         : {updates['error']}")
    print(f"rag_context   : {len(updates.get('rag_context') or [])} CWE chunks retrieved")

    if updates.get("threats"):
        print(f"\nTHREAT MODEL  ({len(updates['threats'])} threats)")
        print("=" * 60)
        for i, t in enumerate(updates["threats"], 1):
            print(f"\n[{i}] {t['cwe_id']} - {t['name']}  [{t['severity']}]")
            print(f"     Description : {t['description']}")
            print(f"     Mitigation  : {t['mitigation']}")


if __name__ == "__main__":
    import sys
    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        print("Run with --test to test the Threat Modeller agent standalone.")
