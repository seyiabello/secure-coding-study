# Planner Agent

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Node-1C3C3C?style=flat)
![Stage](https://img.shields.io/badge/Pipeline%20Stage-1%20of%205-6366F1?style=flat)
![Output](https://img.shields.io/badge/Output-Structured%20JSON-22c55e?style=flat)

First agent in the five-stage multi-agent pipeline. Before a single line of code is written, the Planner reads the coding task and produces an implementation plan with explicit security requirements. Every agent that runs after it works from that foundation.

---

## Architecture

![Planner architecture](../../../screenshots/planner%20agent%20architecture.PNG)

```
Participant's coding task
          |
    run_planner(state)
          |
      GPT-4o call
  JSON mode, temp 0.2
          |
     PlannerOutput
   steps: [ ... ]
   scope: "..."
   security_requirements: [ ... ]
          |
    HITL checkpoint
  Participant approves,
  revises, or adjusts
          |
  Threat Modeller (stage 2)
```

---

## What it produces

**Steps** are ordered, concrete implementation tasks for the Code Generator. Not vague intentions like "handle authentication securely" but specific actions like "hash the password with bcrypt before comparing against the stored hash."

**Scope** is one sentence defining what the code should do and, just as importantly, what it should not do. The "should not" part matters. Without it, the Code Generator might add features that expand the attack surface. Scope is a security decision as much as a design one.

**Security requirements** are the properties the final code must satisfy, identified before any code exists. This is the most significant output. The baseline agent never does this. It jumps straight to code generation. The Planner forces an explicit answer to "what must be secure?" as the very first step.

---

## See it running

![Planner response](../../../screenshots/planner%20agent%20response.PNG)

For the task "Write a Python function that checks a username and password against a SQLite database", the Planner produced steps that named bcrypt as the required hashing approach, a scope that explicitly excluded sessions and registration, and security requirements that called out parameterised queries and safe error message handling by name.

No code has been written yet at this point. That is the entire idea.

---

## Inside the code

![planner.py source 1](../../../screenshots/planner.py%201.PNG)
![planner.py source 2](../../../screenshots/planner.py%202.PNG)

`run_planner()` is an async LangGraph node. It calls GPT-4o using `response_format=json_object` to guarantee structured output, validates the returned fields with safe defaults, and returns a partial state update. LangGraph merges that update back into the shared pipeline state automatically. Errors are captured in state rather than propagated as exceptions.

---

## Key design decisions

**Why no RAG and no MCP here?** The Planner's job is scope and structure, not threat analysis. Pulling CWE data at this stage would conflate planning with threat modelling and make the Threat Modeller redundant. The separation keeps each agent's responsibility clear and testable.

**Why explicit security requirements in the plan, not just steps?** The Code Reviewer and Verifier use these requirements as a checklist. Without them, "review against security requirements" is undefined. The Planner makes the requirements concrete enough that later agents can make a pass/fail judgement on each one.

---

## Running standalone

```bash
# From the project root
python -m multiagent.agents.planner --test
```

---

## Where it fits

| Stage | Agent | Tools |
|---|---|---|
| 1 | **Planner** (this agent) | None |
| 2 | Threat Modeller | RAG, NIST NVD via MCP |
| 3 | Code Generator | HITL hints |
| 4 | Code Reviewer | Bandit via MCP |
| 5 | Verifier | Bandit + Sandbox via MCP, RAG |
