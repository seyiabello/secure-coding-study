# Security Planner Agent

**MSc Research Project · University of Exeter · COMM514**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Node-1C3C3C?style=flat&logo=langchain&logoColor=white)
![Async](https://img.shields.io/badge/Python-Async-3776AB?style=flat&logo=python&logoColor=white)
![Temp](https://img.shields.io/badge/Temperature-0.2-F97316?style=flat)
![Output](https://img.shields.io/badge/Output-Structured%20JSON-6366F1?style=flat)
![Research](https://img.shields.io/badge/University%20of%20Exeter-MSc%20Research-003c71?style=flat)

The first agent in a five-stage multi-agent pipeline for secure code generation. Before a single line of code is written, the Planner reads the coding task and produces a structured implementation plan: ordered steps, a scoped boundary, and explicit security requirements. Every agent that runs after it works from that foundation.

This is part of a controlled experiment comparing a single-agent baseline against a human-orchestrated multi-agent system for secure code generation.

---

## Architecture

![Planner agent architecture](screenshots/planner%20agent%20architecture.PNG)

The Planner sits at the front of the pipeline. It takes the participant's raw task and turns it into a structured plan before any code generation begins.

```
Participant's Coding Task
          |
    run_planner(state)
          |
     System Prompt
          +
       GPT-4o
    temp: 0.2, JSON mode
          |
     PlannerOutput
    steps [ ]
    scope "..."
    security_requirements [ ]
          |
    AgentState updated
          |
    Threat Modeller (next agent)
```

The plan is not a suggestion. It is a contract. The Code Generator follows the steps, the Code Reviewer checks against the security requirements, and the Verifier validates the final code against them. Getting the planning stage right matters.

---

## What it produces

The Planner outputs three things every time it runs:

**Steps** are ordered, concrete implementation tasks written for the Code Generator. Not vague intentions like "handle passwords securely" but specific actions like "hash the password with bcrypt before comparing against the stored hash." The Code Generator follows these directly.

**Scope** is one sentence defining what the code should do and what it should not do. The "should not" part matters. Without it, the Code Generator might add features that increase attack surface. Scope is a security decision as much as a design one.

**Security requirements** are the properties the final code must satisfy, decided before any code exists. This is the most important output. The baseline agent never does this. It jumps straight to code. The Planner forces an explicit answer to "what must be secure?" before a single line is written.

---

## See it in action

![Planner agent terminal output](screenshots/planner%20agent%20response.PNG)

For the task "Write a Python function that checks a username and password against a SQLite database", the Planner produced:

- Scope that explicitly excluded sessions, registration, and password resets
- Steps that identified bcrypt as the required hashing approach
- Security requirements that called out parameterised queries and error message handling specifically

No code has been written yet at this point. That is the whole idea.

---

## Inside the code

![planner.py part 1](screenshots/planner.py%201.PNG)

The system prompt is where the security thinking lives. It instructs GPT-4o to produce task-specific security requirements with explicit examples of what good looks like versus generic noise. The difference between "use bcrypt for password hashing" and "be secure" is the difference between a requirement that can be tested and one that cannot.

![planner.py part 2](screenshots/planner.py%202.PNG)

The `run_planner()` function is an async LangGraph node. It calls GPT-4o directly using the OpenAI SDK with `response_format=json_object` to guarantee structured output, validates the returned fields with safe defaults, and returns a partial state update that LangGraph merges back into the shared pipeline state. If the call fails, the error is captured and stored in state rather than crashing the pipeline.

---

## How to run it

**1. Clone the repo and install dependencies**

```bash
pip install openai python-dotenv langchain-mcp-adapters chromadb
```

**2. Add your OpenAI API key**

Create a `.env` file in the project root:

```
OPENAI_API_KEY=your-key-here
```

**3. Run the standalone test**

```bash
python -m multiagent.agents.planner --test
```

This runs the Planner against a sample login function task and prints the full plan including scope, steps, and security requirements.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| LLM | GPT-4o via OpenAI API |
| Orchestration | LangGraph (async node) |
| State | TypedDict (AgentState, PlannerOutput) |
| Output | Structured JSON via response_format |
| Config | python-dotenv, shared config.py |

---

## Where it fits

This is the first of five agents in the multi-agent pipeline:

1. **Planner** (this agent) breaks the task into steps and defines security requirements
2. **Threat Modeller** runs RAG over the MITRE CWE Top 25 and queries NIST NVD for real CVEs
3. **Code Generator** writes code informed by the plan and threat model
4. **Code Reviewer** runs Bandit static analysis via MCP and critiques the output
5. **Verifier** validates the final code against the original threat model

The human participant reviews and approves, revises, or overrides the output at every stage. The full system uses ChromaDB for vector search, LangGraph for orchestration, and MCP tool servers for Bandit, NIST NVD, and sandboxed code execution.

The experiment will measure whether this structured approach produces less vulnerable code than the single-agent baseline.

---

## Research context

This project is part of an MSc dissertation at the University of Exeter (COMM514). It is a controlled experiment, not a production tool. Participants are computer science and software engineering students. All sessions are anonymised.

> Supervisor confirmed: the added complexity is justified if it improves output quality. The goal is to build something that actually works better, not just something more complicated.
