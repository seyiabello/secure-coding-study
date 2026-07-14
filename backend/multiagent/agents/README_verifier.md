# Verifier Agent

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![Bandit](https://img.shields.io/badge/Static%20Analysis-Bandit%20via%20MCP-dc2626?style=flat)
![Sandbox](https://img.shields.io/badge/Execution-Sandboxed%20via%20MCP-6366F1?style=flat)
![RAG](https://img.shields.io/badge/RAG-CWE%20Top%2025-F97316?style=flat)
![Stage](https://img.shields.io/badge/Pipeline%20Stage-5%20of%205-6366F1?style=flat)

Fifth and final agent in the pipeline. Runs four independent checks to produce a per-threat PASS or FAIL verdict on the submitted code, with an overall assessment. This is the last thing that runs before the session is logged.

---

## Architecture

![Verifier architecture](../../../screenshots/verifier%20architecture.PNG)

```
Code Reviewer findings reviewed by participant
               |
   run_verifier(state)
               |
   +-----+-----+-----+-----+
   |     |     |     |     |
Bandit  Sand  RAG  (all
via    boxed  re-  three
MCP    exec-  query run in
       ution  CWE  parallel)
       via    corpus
       MCP
   +-----+-----+-----+-----+
               |
          GPT-4o synthesis
          Per-threat verdict:
          PASS or FAIL
          + overall assessment
               |
   VerificationResult in state
               |
    Finalise node logs session
```

---

## Four independent checks

**Bandit via MCP:** A second independent static analysis run, separate from the Code Reviewer's run. Results are stored as `bandit_findings_verify`. Never merged with `bandit_findings_review`. Two separate calls, two separate state fields.

**Sandboxed execution via MCP:** The code is executed inside an isolated environment. The Verifier checks whether it runs without errors, not whether it is correct in all inputs. Runtime errors that escape static analysis get caught here.

**RAG re-query of CWE Top 25:** The Verifier retrieves CWE data independently of the Threat Modeller. This re-grounding ensures the final verdict is anchored in the same published standards the threat model was built from, without copying the Threat Modeller's specific context.

**GPT-4o synthesis:** Takes all three tool outputs plus the original threat model and produces a structured verdict: PASS or FAIL for each threat, with an explanation, and an overall assessment of the code's security posture.

---

## Output schema

```json
{
  "overall_verdict": "PARTIAL_PASS",
  "threat_results": [
    {
      "cwe_id": "CWE-89",
      "verdict": "PASS",
      "evidence": "Parameterised query used correctly at line 14.",
      "confidence": "high"
    },
    {
      "cwe_id": "CWE-20",
      "verdict": "FAIL",
      "evidence": "Username is not validated for type or length before the query.",
      "confidence": "medium"
    }
  ],
  "execution_result": {
    "ran_without_error": true,
    "output": ""
  },
  "summary": "The SQL injection risk is correctly addressed. Input validation is missing."
}
```

---

## See it running

![Verifier response](../../../screenshots/verifier%20response.PNG)

![Verifier source](../../../screenshots/verifier%20code%20snippet.PNG)

---

## Key design decisions

**Why four checks rather than just repeating Bandit?** Each tool catches different things. Bandit is great for known Python security patterns but cannot reason about whether a mitigation was correctly applied in context. The LLM can reason about intent but may miss exact-line issues. The sandbox catches runtime failures neither tool can predict from static analysis. RAG re-grounding keeps the verdicts tied to published standards rather than the model's priors.

**Why does the Verifier run independently after the Code Reviewer rather than before?** The Code Reviewer's findings go to the participant as feedback. The Verifier's role is final verdict, not feedback. Running them in this order means the participant has had one chance to respond to findings before the final assessment is made.

**Why are the two Bandit runs in separate state fields?** If they shared results, the "two independent checks" would be a fiction. Separate fields enforce independence at the data level and make it verifiable in the research logs.

---

## Running standalone

```bash
# From the project root
python -m multiagent.agents.verifier --test
```

---

## Where it fits

| Stage | Agent | Tools |
|---|---|---|
| 1 | Planner | None |
| 2 | Threat Modeller | RAG (ChromaDB), NIST NVD via MCP |
| 3 | Code Generator | Step classifier, adaptive hints |
| 4 | Code Reviewer | Bandit via MCP |
| 5 | **Verifier** (this agent) | Bandit via MCP, Sandbox via MCP, RAG |
