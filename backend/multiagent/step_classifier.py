"""
multiagent/step_classifier.py
------------------------------
Classifies each Planner step by its maximum hint level.

Run once after the threat model is approved. Uses one GPT-4o call to match
each step against the threat model mitigations and assign a cap:

  "direction"  — step directly implements a named threat mitigation.
                 Only plain-English hints are revealed; no code ever shown.
  "pseudocode" — step is security-adjacent (touches sensitive data or logic)
                 but is not the core mitigation. Pseudocode is the ceiling.
  "partial"    — general logic step. Partial implementation (with TODOs) allowed.
  "full"       — pure boilerplate (imports, DB connection, resource cleanup).
                 Full code may be shown because the security work is elsewhere.

The result is stored in state["step_hint_caps"] and returned to the frontend
via GET /session/{thread_id}/step-caps.
"""

import json

from config import MODEL, client

# ── Classification prompt ──────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are classifying the steps of a secure coding task by their security sensitivity.

You will receive a list of numbered implementation steps and a list of security
threats with their mitigations.

For each step assign exactly one of these max_hint_level values:

  "full"       — Pure boilerplate: imports, opening/closing DB connections,
                 variable declarations, resource cleanup. The participant cannot
                 introduce a security vulnerability by implementing this step
                 incorrectly. Show full code.

  "partial"    — General logic: control flow, return values, comparisons, error
                 handling that doesn't involve security-critical sanitisation.
                 Show partial implementation with TODO markers for anything
                 security-sensitive within this step.

  "pseudocode" — The step involves data or logic that could be mishandled
                 (e.g. passing user input to a function, building a query,
                 calling an API) but is not the primary location of the
                 security mitigation. Show pseudocode only.

  "direction"  — The step IS the security-critical implementation. It directly
                 and primarily carries out a mitigation named in the threat model
                 (e.g. "use parameterised queries", "hash with bcrypt", "validate
                 and sanitise input", "check permissions"). Never show code.

Assignment rules:
- Read each threat's mitigation carefully. If a step is where that mitigation
  is implemented, assign "direction".
- A step that only sets up the environment for security work (e.g. opening a
  connection before running a parameterised query) is "full" or "partial",
  not "direction" — the security work happens in the query step itself.
- When uncertain, assign one level stricter (e.g. prefer "pseudocode" over "partial").
- Every step must get exactly one level.

Respond with valid JSON only — no markdown, no explanation outside the JSON:
{
  "step_caps": [
    {
      "step_index": 0,
      "max_level": "full",
      "reason": "one sentence explaining this classification"
    }
  ]
}"""

# Map level strings to integers for ordering/comparison
LEVEL_ORDER = {"direction": 1, "pseudocode": 2, "partial": 3, "full": 4}
VALID_LEVELS = set(LEVEL_ORDER.keys())


def classify_steps(plan: dict, threats: list[dict]) -> list[dict]:
    """
    Classifies each plan step by its maximum hint level.

    Parameters
    ----------
    plan : dict
        PlannerOutput with "steps" (list[str]) and "security_requirements".
    threats : list[dict]
        ThreatEntry list from the Threat Modeller.

    Returns
    -------
    list[dict]
        One entry per step: { step_index, max_level, reason }.
        Falls back to "pseudocode" for all steps if the LLM call fails.
    """
    steps = plan.get("steps", [])
    if not steps:
        return []

    steps_text = "\n".join(f"{i}. {s}" for i, s in enumerate(steps))
    threats_text = "\n".join(
        f"  [{t['cwe_id']}: {t['name']}]\n"
        f"    Mitigation: {t['mitigation']}"
        for t in threats
    )

    user_message = (
        f"Implementation steps:\n{steps_text}\n\n"
        f"Threat model mitigations:\n{threats_text}"
    )

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user",   "content": user_message},
            ],
        )
        data = json.loads(response.choices[0].message.content)
        raw_caps = data.get("step_caps", [])

        # Normalise: one entry per step, validate level, fill gaps with "pseudocode"
        index_to_cap = {c["step_index"]: c for c in raw_caps if isinstance(c.get("step_index"), int)}
        result = []
        for i in range(len(steps)):
            cap = index_to_cap.get(i)
            level = cap.get("max_level", "pseudocode") if cap else "pseudocode"
            if level not in VALID_LEVELS:
                level = "pseudocode"
            result.append({
                "step_index": i,
                "max_level":  level,
                "reason":     cap.get("reason", "classification default") if cap else "step not returned by classifier",
            })

        print(f"[StepClassifier] Classified {len(result)} steps: "
              f"{[r['max_level'] for r in result]}")
        return result

    except Exception as exc:
        print(f"[StepClassifier] Classification failed: {exc} — defaulting all to 'pseudocode'")
        return [
            {"step_index": i, "max_level": "pseudocode", "reason": "classification failed"}
            for i in range(len(steps))
        ]
