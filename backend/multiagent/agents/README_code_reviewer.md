# Code Reviewer Agent

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![Bandit](https://img.shields.io/badge/Static%20Analysis-Bandit%20via%20MCP-dc2626?style=flat)
![Stage](https://img.shields.io/badge/Pipeline%20Stage-4%20of%205-6366F1?style=flat)

Fourth agent in the pipeline. Runs two independent security checks on the participant's code and produces a structured list of findings that the participant reviews before the Verifier runs.

---

## Architecture

![Code Reviewer architecture](../../../screenshots/code_reviewer%20architecture.PNG)

```
Participant's submitted code + threat model
               |
   run_code_reviewer(state)
               |
       +-------+-------+
       |               |
  Bandit via MCP    GPT-4o LLM review
  Static analysis   Checks each threat
  Python security   mitigation against
  linter, full run  the actual code
       |               |
       +-------+-------+
               |
    Findings merged and deduplicated
    ReviewFinding list in state
    (stored as bandit_findings_review,
     separate from Verifier's run)
               |
       HITL checkpoint
    Participant reads findings,
    decides how to respond
               |
       Verifier (stage 5)
```

---

## What it produces

A list of `ReviewFinding` objects, one per issue:

```json
{
  "cwe_id": "CWE-89",
  "severity": "Critical",
  "description": "The query concatenates username using an f-string. An attacker can inject arbitrary SQL.",
  "suggested_fix": "Replace the f-string with a parameterised query: cursor.execute('SELECT * FROM users WHERE username = ?', (username,))",
  "line_number": 14,
  "source": "bandit"
}
```

Both Bandit and the LLM produce findings in this format. They are merged into one list so the participant sees a single, prioritised view.

---

## Two independent checks

**Bandit via MCP:** Industry-standard Python static analysis. Runs on the submitted code as a subprocess inside the Bandit MCP server. The raw findings are stored in `bandit_findings_review` in state.

**LLM review via GPT-4o:** Takes the submitted code and the threat model's mitigation list and checks each mitigation explicitly. This catches things Bandit cannot: logical security flaws, missing validation, incorrect use of a library, or correct-looking code that implements the wrong thing. The LLM review complements rather than duplicates Bandit.

---

## Why findings are stored separately from the Verifier's run

The Verifier also runs Bandit, stored as `bandit_findings_verify`. These two state fields must never be merged or shared. The Verifier is a genuine independent second check. If both agents worked from the same Bandit results, the pipeline would look like it was checking twice when it was really checking once.

---

## See it running

![Code Reviewer response](../../../screenshots/code_reviewer%20response.PNG)

![Code Reviewer source](../../../screenshots/code_reviewer%20code%20snippet.PNG)

---

## Key design decisions

**Why does the participant review findings rather than having the agent automatically fix the code?** The study is about human-in-the-loop behaviour. If the system auto-fixed the code, the participant would never engage with the security findings and the HITL stage would be meaningless. Making them read and respond to findings is the research instrument.

**Why merge Bandit and LLM findings into one list?** Presenting two separate lists creates cognitive load that works against the study. Participants need to understand the security picture of their code, not navigate between tool outputs. One unified list with a `source` field for provenance is cleaner.

---

## Running standalone

```bash
# From the project root
python -m multiagent.agents.code_reviewer --test
```

---

## Where it fits

| Stage | Agent | Tools |
|---|---|---|
| 1 | Planner | None |
| 2 | Threat Modeller | RAG (ChromaDB), NIST NVD via MCP |
| 3 | Code Generator | Step classifier, adaptive hints |
| 4 | **Code Reviewer** (this agent) | Bandit via MCP |
| 5 | Verifier | Bandit + Sandbox via MCP, RAG |
