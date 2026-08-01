"""
evaluation/langfuse_eval.py
---------------------------
LLM-as-judge evaluation functions for the secure coding study.

Three evaluators run automatically at the end of every multi-agent session:

  1. rag_quality: did the Threat Modeller retrieve the right CWEs?
  2. review_groundedness: are Code Reviewer findings grounded in the actual code?
  3. bandit_agreement: do Code Reviewer and Verifier agree on Bandit results?

run_all_evals() is decorated with @observe so all three judge calls appear as
a single "eval_session" trace in Langfuse, grouped under the same session_id
as the agent traces. Scores are pushed to the trace via score_current_trace().

Results are also returned as a dict that _finalise() embeds in the JSONL log
under multi_agent_detail.eval, so they survive without a Langfuse account.
"""

import json
from typing import Optional

try:
    from langfuse import observe, propagate_attributes, get_client as _get_lf
    _lf = _get_lf()
    _LANGFUSE = True
except Exception:
    _LANGFUSE = False
    _lf = None
    # No-op stubs so the module loads without Langfuse installed.
    from contextlib import nullcontext as propagate_attributes  # type: ignore
    def observe(*a, **kw):                                      # type: ignore
        def decorator(fn): return fn
        return decorator

from config import MODEL, client

_JUDGE_TEMP = 0.0


# ── 1. RAG Quality Judge ───────────────────────────────────────────────────────

_RAG_PROMPT = """\
You are an expert security evaluator assessing the quality of CWE retrieval \
for a coding task.

Task: {task}

CWEs retrieved from the MITRE Top 25 corpus:
{retrieved_cwes}

Threats produced by the Threat Modeller using this retrieval:
{threats}

Rate the retrieval quality 0–10:
  10  = retrieved CWEs perfectly match the actual vulnerabilities in this task
  7-9 = highly relevant, minor gaps
  4-6 = partially relevant, some important CWEs missing
  1-3 = mostly irrelevant or missing critical ones
  0   = completely wrong CWEs

Respond with valid JSON only:
{{
  "score": <0-10>,
  "reasoning": "One sentence explaining the score.",
  "missed_cwes": ["CWE-XX"],
  "irrelevant_cwes": ["CWE-XX"]
}}"""


def score_rag_quality(task: str, rag_results: list, threats: list) -> dict:
    """
    LLM-as-judge: score the Threat Modeller's RAG retrieval quality (0–10).
    Called from inside run_all_evals() which owns the Langfuse trace context.
    """
    retrieved_cwes = "\n".join(
        f"- {r.get('metadata', {}).get('cwe_id', '?')}: "
        f"{r.get('metadata', {}).get('short_name', '')}"
        for r in (rag_results or [])
    ) or "None retrieved"

    threats_text = "\n".join(
        f"- {t['cwe_id']}: {t['name']} [{t['severity']}]"
        for t in (threats or [])
    ) or "No threats produced"

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=_JUDGE_TEMP,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": _RAG_PROMPT.format(
                    task=task,
                    retrieved_cwes=retrieved_cwes,
                    threats=threats_text,
                ),
            }],
            name="judge/rag_quality",
        )
        result = json.loads(response.choices[0].message.content)
        print(f"[Eval] RAG quality: {result.get('score')}/10: {result.get('reasoning', '')}")
        return result
    except Exception as exc:
        print(f"[Eval] RAG quality judge failed: {exc}")
        return {"score": None, "error": str(exc)}


# ── 2. Review Groundedness Judge ───────────────────────────────────────────────

_GROUNDEDNESS_PROMPT = """\
You are a security code review evaluator. Determine whether each finding from \
a code review is grounded in the actual code: i.e., refers to a pattern or \
line that genuinely exists: or is hallucinated.

Code:
```python
{code}
```

Review findings:
{findings}

For each finding decide: grounded (true/false) and cite what you observed.

Respond with valid JSON only:
{{
  "total_findings": <n>,
  "grounded_count": <n>,
  "hallucinated_count": <n>,
  "groundedness_rate": <0.0-1.0>,
  "findings": [
    {{
      "cwe_id": "CWE-XX",
      "grounded": true,
      "reason": "One sentence citing the actual code."
    }}
  ]
}}"""


def score_review_groundedness(
    code: str,
    findings: list,
    agent: str = "code_reviewer",
) -> dict:
    """
    LLM-as-judge: are the Code Reviewer's findings grounded in the actual code?
    Called from inside run_all_evals() which owns the Langfuse trace context.
    """
    if not findings:
        return {
            "total_findings": 0,
            "grounded_count": 0,
            "hallucinated_count": 0,
            "groundedness_rate": 1.0,
            "findings": [],
        }

    findings_text = "\n".join(
        f"- [{f.get('cwe_id', '?')}] {f.get('severity', '?')}: "
        f"{f.get('description', '')} (line {f.get('line_number', '?')})"
        for f in findings
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=_JUDGE_TEMP,
            response_format={"type": "json_object"},
            messages=[{
                "role": "user",
                "content": _GROUNDEDNESS_PROMPT.format(
                    code=code or "(no code provided)",
                    findings=findings_text,
                ),
            }],
            name=f"judge/groundedness_{agent}",
        )
        result = json.loads(response.choices[0].message.content)
        rate = result.get("groundedness_rate", 0)
        print(
            f"[Eval] {agent} groundedness: "
            f"{result.get('grounded_count')}/{result.get('total_findings')} "
            f"({rate:.0%})"
        )
        return result
    except Exception as exc:
        print(f"[Eval] Groundedness judge failed ({agent}): {exc}")
        return {"groundedness_rate": None, "error": str(exc)}


# ── 3. Cross-Agent Bandit Agreement ───────────────────────────────────────────

def compute_bandit_agreement(bandit_review: list, bandit_verify: list) -> dict:
    """
    Compute Jaccard overlap between Code Reviewer and Verifier Bandit runs.

    Both agents run Bandit on the same code: they should agree on CWE findings.
    Disagreement flags a state bug, non-deterministic Bandit output, or MCP error.
    No LLM call needed: this is a deterministic computation.
    """
    review_cwes = {f.get("cwe_id") for f in (bandit_review or []) if f.get("cwe_id")}
    verify_cwes  = {f.get("cwe_id") for f in (bandit_verify  or []) if f.get("cwe_id")}

    union        = review_cwes | verify_cwes
    intersection = review_cwes & verify_cwes
    agreement    = len(intersection) / len(union) if union else 1.0

    result = {
        "agreement_score": round(agreement, 3),
        "review_cwes":     sorted(review_cwes),
        "verify_cwes":     sorted(verify_cwes),
        "only_in_review":  sorted(review_cwes - verify_cwes),
        "only_in_verify":  sorted(verify_cwes  - review_cwes),
        "review_count":    len(bandit_review or []),
        "verify_count":    len(bandit_verify  or []),
    }

    print(
        f"[Eval] Bandit agreement: {agreement:.0%} "
        f"(reviewer={result['review_count']}, verifier={result['verify_count']})"
    )
    return result


# ── Combined runner ────────────────────────────────────────────────────────────

@observe(name="eval_session")
def run_all_evals(state: dict) -> dict:
    """
    Run all three evaluators at session completion and push scores to Langfuse.

    Decorated with @observe so all three judge calls appear as a single
    "eval_session" trace in Langfuse. propagate_attributes() sets the same
    session_id and user_id used by the agent traces so they are grouped
    together in the Sessions view.

    Called from graph._finalise(). Returns a dict that is embedded in the
    JSONL log under multi_agent_detail.eval.
    """
    participant_id = state.get("participant_id", "unknown")
    task_id        = state.get("task_id", "unknown")
    session_id     = f"{participant_id}_{task_id}"

    with propagate_attributes(
        session_id=session_id,
        user_id=participant_id,
        tags=["eval"],
    ):
        rag = score_rag_quality(
            task=state.get("task", ""),
            rag_results=state.get("rag_context") or [],
            threats=state.get("threats") or [],
        )

        groundedness = score_review_groundedness(
            code=state.get("generated_code") or "",
            findings=state.get("review_findings") or [],
            agent="code_reviewer",
        )

        agreement = compute_bandit_agreement(
            bandit_review=state.get("bandit_findings_review") or [],
            bandit_verify=state.get("bandit_findings_verify") or [],
        )

    # Push numeric scores to the eval_session trace in Langfuse.
    if _LANGFUSE and _lf:
        try:
            rag_score = rag.get("score")
            if rag_score is not None:
                _lf.score_current_trace(
                    name="rag_quality",
                    value=float(rag_score) / 10.0,
                    data_type="NUMERIC",
                    comment=rag.get("reasoning", ""),
                )

            gr_rate = groundedness.get("groundedness_rate")
            if gr_rate is not None:
                _lf.score_current_trace(
                    name="review_groundedness",
                    value=float(gr_rate),
                    data_type="NUMERIC",
                    comment=(
                        f"{groundedness.get('grounded_count')}/"
                        f"{groundedness.get('total_findings')} findings grounded"
                    ),
                )

            _lf.score_current_trace(
                name="bandit_agreement",
                value=agreement["agreement_score"],
                data_type="NUMERIC",
                comment=(
                    f"reviewer={sorted(agreement['review_cwes'])} | "
                    f"verifier={sorted(agreement['verify_cwes'])}"
                ),
            )
        except Exception as exc:
            print(f"[Eval] Score push failed (non-fatal): {exc}")

    return {
        "rag_quality":         rag,
        "review_groundedness": groundedness,
        "bandit_agreement":    agreement,
    }
