# Code Reviewer Agent

**MSc Research Project · University of Exeter · COMM514**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Node-1C3C3C?style=flat&logo=langchain&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-Bandit-D32F2F?style=flat)
![Bandit](https://img.shields.io/badge/Bandit-Static%20Analysis-FF6F00?style=flat)
![Async](https://img.shields.io/badge/Python-Async-3776AB?style=flat&logo=python&logoColor=white)
![Temp](https://img.shields.io/badge/Temperature-0.2-F97316?style=flat)
![Output](https://img.shields.io/badge/Output-Structured%20JSON-6366F1?style=flat)
![No RAG](https://img.shields.io/badge/RAG-None-lightgrey?style=flat)
![Research](https://img.shields.io/badge/University%20of%20Exeter-MSc%20Research-003c71?style=flat)

The fourth agent in a five-stage multi-agent pipeline for secure code generation. Once the Code Generator has produced a function, the Code Reviewer runs two completely independent security checks on it before anything reaches the human participant. Static analysis via Bandit catches what it can see. GPT-4o catches what Bandit cannot.

Neither check trusts the other. That is the point.

This is part of a controlled experiment comparing a single-agent AI baseline against a human-orchestrated multi-agent system for secure code generation.

---

## Architecture

![Code Reviewer architecture](screenshots/code_reviewer%20architecture.PNG)

The Code Reviewer receives two things from state: the generated code and the threat model that the code was supposed to implement. It then runs two checks in sequence.

First, it calls the `run_bandit` MCP tool, which runs Bandit static analysis on the code inside a local stdio server. The raw findings go straight into `bandit_findings_review` in state, untouched.

Second, it passes the code, the Bandit output, and the threat model to GPT-4o. The LLM is instructed to do two specific things: verify that every mitigation from the threat model was actually implemented correctly, and flag any issues Bandit missed. Every finding gets a `source` field — `"bandit"` or `"llm"` — so the human participant and the evaluation log know exactly where each finding came from.

```
Generated Code  +  Threat Model
        |                 |
   run_bandit          (passed to GPT-4o)
   MCP stdio              |
        |                 |
   Bandit findings ------>|
   (raw, stored           |
    independently)     GPT-4o
                       temp: 0.2 · JSON mode
                       verify mitigations · flag gaps
                          |
                   review_findings
                   source: bandit | llm
                   cwe_id · severity
                   description · suggested_fix
                          |
                       Verifier
```

One architectural rule that matters here: `bandit_findings_review` is stored completely separately from the Verifier's `bandit_findings_verify`. The Verifier runs its own independent Bandit call. These two results never touch each other. The Verifier is a genuine second check, not a repeat of this one.

---

## What it produces

![Code Reviewer terminal output](screenshots/code_reviewer%20response.PNG)

On a deliberately vulnerable version of the login function (f-string SQL query, MD5 password hashing, no input validation), the Code Reviewer returned:

- **CWE-89 (Critical, source: bandit)**: f-string SQL injection on line 8, with the exact parameterised query fix
- **CWE-327 (High, source: bandit)**: MD5 flagged as cryptographically broken, with the bcrypt replacement

GPT-4o then added what Bandit could not see from static analysis alone: the missing input validation and the information leakage from a return message that reveals whether the username or password was wrong.

On the secure version of the same code, both Bandit and GPT-4o returned zero findings. That is also the correct result. The reviewer is not supposed to invent problems that are not there.

---

## Inside the code

![Code Reviewer source code](screenshots/code_reviewer%20code%20snippet.PNG)

The `run_code_reviewer()` function is an async LangGraph node. It makes two external calls: one to the Bandit MCP server and one to GPT-4o. The user message to GPT-4o contains all three pieces of context in labelled sections: the code wrapped in a Python fence, the formatted Bandit output, and the threat model with each mitigation listed for verification.

The `ReviewFinding` list comprehension at the end normalises the GPT-4o output into typed dicts with safe `.get()` defaults on every field. The `source` field is the key one — it tells the evaluation pipeline whether a finding came from static analysis or from the LLM review.

The independence constraint is enforced at the state schema level. `bandit_findings_review` and `bandit_findings_verify` are two separate fields in `AgentState`. There is no code path that copies one into the other.

---

## How to run it

**1. Clone the repo and install dependencies**

```bash
pip install openai langchain-mcp-adapters mcp python-dotenv bandit
```

**2. Add your OpenAI API key**

Create a `.env` file in the project root:

```
OPENAI_API_KEY=your-key-here
```

**3. Run the standalone test**

```bash
python -m multiagent.agents.code_reviewer --test
```

The test runs the reviewer against deliberately vulnerable code (f-string SQL injection, MD5 hashing) and prints the full findings including CWE IDs, severity, source, line numbers, and suggested fixes.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| LLM | GPT-4o via OpenAI API |
| Orchestration | LangGraph (async node) |
| Static analysis | Bandit via MCP stdio server |
| MCP transport | stdio (langchain-mcp-adapters 0.1.0) |
| State | TypedDict (AgentState, ReviewFinding) |
| Output | Structured JSON via response_format |
| Config | python-dotenv, shared config.py |
| RAG | None |

---

## Where it fits

This is the fourth of five agents in the multi-agent pipeline:

1. **Planner** breaks the task into steps and defines security requirements
2. **Threat Modeller** identifies relevant CWEs and live CVEs using RAG and NIST NVD
3. **Code Generator** writes code that follows the plan and implements every mitigation
4. **Code Reviewer** (this agent) runs Bandit and GPT-4o review independently
5. **Verifier** validates the final code against the original threat model using its own Bandit run and a sandbox

The human participant reviews and approves, revises, or overrides the output at every stage. The full system uses ChromaDB for vector search, LangGraph for orchestration, and MCP tool servers for Bandit, NIST NVD, and sandboxed code execution.

---

## Research context

This project is part of an MSc dissertation at the University of Exeter (COMM514). It is a controlled experiment, not a production tool. Participants are computer science and software engineering students. All sessions are anonymised.

The Code Reviewer is where the two-source approach matters most. Bandit is fast and consistent but only catches patterns it has rules for. GPT-4o catches logic errors, missing mitigations, and information leakage that no static analyser would flag. Running both and labelling the source of every finding is what makes the output useful for analysis rather than just a pass/fail verdict.
