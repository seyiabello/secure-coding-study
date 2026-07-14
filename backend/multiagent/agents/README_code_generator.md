# Code Generator Agent

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![HITL](https://img.shields.io/badge/HITL-Human%20writes%20the%20code-22c55e?style=flat)
![Hints](https://img.shields.io/badge/Hints-Per--step%20with%20security%20caps-F97316?style=flat)
![Stage](https://img.shields.io/badge/Pipeline%20Stage-3%20of%205-6366F1?style=flat)

Third agent in the pipeline. Unlike every other agent here, this one does not generate the code. The participant writes the code themselves, with access to a structured hint system informed by the threat model.

---

## Architecture

![Code Generator architecture](../../../screenshots/code_generator%20architecture.PNG)

```
Approved plan + approved threat model
               |
   run_code_generator() sets stage
   to "coding_in_progress", no code
               |
   HITL: participant writes code
   in the Monaco editor
               |
   +-----------+-----------+
   |           |           |
Step hints  Adaptive   Security
per-step    next-hint   hint
hint caps   on demand   on demand
(GPT-4o)   (reads code) (Bandit +
               |           LLM)
   +-----------+-----------+
               |
   Participant submits code
               |
    finalize_code() stores:
    user_code, annotations,
    confidence, hints log,
    time in coding
               |
  Code Reviewer (stage 4)
```

---

## The hint system

This is the most technically complex part of the pipeline. The participant can request four levels of hint per plan step:

| Level | What they get |
|---|---|
| Direction | Plain English description of what to do and why |
| Pseudocode | Algorithmic structure with no implementation details |
| Partial Code | Working code with security-critical sections left as TODO |
| Full Code | Complete implementation |

Hints are sequential. You cannot request Pseudocode without first requesting Direction. This prevents participants from jumping straight to the answer.

**Security caps:** Not all steps allow all four levels. The step classifier makes one GPT-4o call after the threat model is approved and assigns each step a maximum hint level based on how directly it implements a threat mitigation. A step that IS the security-critical implementation (for example, "use a parameterised query") is capped at Direction only. Full code is never shown for that step. A pure boilerplate step (opening a database connection, importing modules) can go all the way to Full.

**Adaptive hint:** A global "What should I do next?" button reads the participant's actual code and identifies what has been done, what is missing, and what looks incorrect. It adapts to however the participant has chosen to structure their implementation rather than assuming they are following the plan steps in order.

**Security hint:** A separate "Analyse Code" button runs a whole-code security pass at any time. It flags the single most pressing security issue in the current code, referenced to its CWE where relevant.

---

## See it running

![Code Generator response](../../../screenshots/code_generator%20response.PNG)

![Code Generator source](../../../screenshots/code%20generator%20file%20snipet.PNG)

---

## What gets logged

When the participant submits, `finalize_code()` records:

- The code as written by the participant
- Annotations: what they say the code does, which threats they believe they addressed, and their confidence rating (1 to 5)
- The full hint log: which hints were requested, at which level, and when
- Time spent in the coding stage in seconds
- Optional pre-review prediction: which vulnerabilities they expect the reviewer to flag

The hint log is a research instrument. It shows how much help each participant needed and at what level, and that data is part of the study's secondary analysis.

---

## Key design decisions

**Why does the participant write the code rather than the agent?** The study is about human behaviour in AI-assisted coding, not about AI-to-AI quality. If an agent wrote the code, the baseline and multi-agent conditions would both be pure AI output and the comparison would collapse.

**Why are hint caps based on the threat model?** Participants who jump straight to Full Code for security-critical steps effectively skip the security work. Capping those steps forces engagement. The caps are computed automatically by matching steps to threat mitigations, so they are specific to each task.

**Why a global adaptive hint rather than forcing step-by-step navigation?** People code non-linearly. Some write all the imports first, some start with the core logic, some jump between sections. Forcing step-by-step navigation would create artificial friction. The adaptive hint meets participants where their code actually is.

---

## Running standalone

```bash
# From the project root
python -m multiagent.agents.code_generator --test
```

---

## Where it fits

| Stage | Agent | Tools |
|---|---|---|
| 1 | Planner | None |
| 2 | Threat Modeller | RAG (ChromaDB), NIST NVD via MCP |
| 3 | **Code Generator** (this agent) | Step classifier (GPT-4o), adaptive hints |
| 4 | Code Reviewer | Bandit via MCP |
| 5 | Verifier | Bandit + Sandbox via MCP, RAG |
