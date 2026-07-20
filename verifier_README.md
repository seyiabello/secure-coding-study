# Verifier Agent

**MSc Research Project · University of Exeter · COMM514**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Node-1C3C3C?style=flat&logo=langchain&logoColor=white)
![RAG](https://img.shields.io/badge/RAG-ChromaDB-FF6F00?style=flat&logo=databricks&logoColor=white)
![MCP Bandit](https://img.shields.io/badge/MCP-Bandit-D32F2F?style=flat)
![MCP Sandbox](https://img.shields.io/badge/MCP-Sandbox-E65100?style=flat)
![Async](https://img.shields.io/badge/Python-Async-3776AB?style=flat&logo=python&logoColor=white)
![Temp](https://img.shields.io/badge/Temperature-0.2-F97316?style=flat)
![Output](https://img.shields.io/badge/Output-Structured%20JSON-6366F1?style=flat)
![Research](https://img.shields.io/badge/University%20of%20Exeter-MSc%20Research-003c71?style=flat)

The fifth and final agent in a five-stage multi-agent pipeline for secure code generation. The Verifier does not ask whether the code looks good. It asks a more specific question: did the code implement every mitigation from the original threat model, and does it actually run?

Four independent checks. None of them share results with the Code Reviewer that ran before it.

This is part of a controlled experiment comparing a single-agent AI baseline against a human-orchestrated multi-agent system for secure code generation.

---

## Architecture

![Verifier architecture](screenshots/verifier%20architecture.PNG)

The Verifier runs four checks in sequence, all independent from each other and from the Code Reviewer.

First, it calls the `run_bandit` MCP tool for its own static analysis run. The results go into `bandit_findings_verify`, a completely separate state field from the Code Reviewer's `bandit_findings_review`. They are never merged.

Second, it calls the `execute_code` MCP tool, which runs the code inside a sandboxed subprocess with a timeout enforced. Exit code, stdout, and stderr are all captured.

Third, it runs the full Advanced RAG pipeline against the CWE corpus independently, using the original coding task as the query. It arrives at its own CWE context without being told what the Threat Modeller found.

Finally, all five inputs — the code, the threat model, the Bandit findings, the CWE context, and the sandbox result — are assembled into a single user message and passed to GPT-4o. The LLM gives a PASS or FAIL verdict for each threat in the original threat model, with specific notes citing the actual lines of code it observed.

```
Generated Code      +      Threat Model
       |                        |
  run_bandit    execute_code   RAG
  MCP stdio     MCP stdio     CWE corpus
  (independent) (sandbox)     (independent)
       |             |             |
       └─────────────┴─────────────┘
                     |
              Prompt Assembly
        code + threats + findings
        + CWE context + exec result
                     |
                  GPT-4o
          temp: 0.2 · JSON mode
      per-threat PASS/FAIL verdict
      strict: partial = FAIL
                     |
          VerificationResult
          overall_pass
          threats_checked (per CWE)
          bandit_findings
          execution_result
          notes
          final_code → evaluation log
          current_stage: complete
```

---

## What it produces

![Verifier terminal output](screenshots/verifier%20response.PNG)

For the login function task with the secure code, the Verifier returned:

- Bandit: 0 findings (independent run)
- Sandbox: `passed=True`, `exit_code=0`
- RAG: independently retrieved CWE-89, CWE-639, CWE-20 without being told what the Threat Modeller found
- CWE-89 PASS: "Parameterised query with ? placeholder used on line 10. No string concatenation in SQL."
- CWE-20 PASS: "Input validation checks ensure username and password are strings and within length limits on lines 4-6."
- Overall: PASS

The notes cite specific lines. That is the requirement. "The code looks secure" is not an acceptable output from this agent.

---

## Inside the code

![Verifier source code](screenshots/verifier%20code%20snippet.PNG)

The `run_verifier()` function is an async LangGraph node. It makes three external calls before GPT-4o sees anything: Bandit via MCP, the sandbox via MCP, and the RAG retriever. Each call is awaited in sequence. The results from all three, plus the code and the threat model, are assembled into one user message with clearly labelled sections.

The `VerificationResult` TypedDict normalises the GPT-4o output into a typed structure. `overall_pass` is a boolean that is true only when all per-threat checks passed and the sandbox returned exit code 0. The `threats_checked` list maps each CWE ID from the original threat model to a verdict and a note.

The independence constraint is structural. `bandit_findings_verify` and `bandit_findings_review` are two separate fields in `AgentState`. There is no code path that reads one to populate the other.

`final_code` is set to the generated code regardless of the verdict. The code is what it is. The verdict lives in `verification_result`. Both go into the evaluation log.

---

## How to run it

**1. Clone the repo and install dependencies**

```bash
pip install openai langchain-mcp-adapters mcp python-dotenv bandit chromadb
```

**2. Add your OpenAI API key**

Create a `.env` file in the project root:

```
OPENAI_API_KEY=your-key-here
```

**3. Ingest the CWE corpus**

```bash
python -m rag.ingest
```

This only runs once. It embeds the MITRE CWE Top 25 into a local ChromaDB collection.

**4. Run the standalone test**

```bash
python -m multiagent.agents.verifier --test
```

This runs the full Verifier pipeline against a pre-built login function task and prints the per-threat verdicts, sandbox result, and overall pass/fail.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| LLM | GPT-4o via OpenAI API |
| Orchestration | LangGraph (async node) |
| Static analysis | Bandit via MCP stdio server (independent) |
| Sandbox execution | Custom MCP stdio server (subprocess + timeout) |
| RAG | ChromaDB + text-embedding-3-small (independent) |
| Corpus | MITRE CWE Top 25 (2025) |
| MCP transport | stdio (langchain-mcp-adapters 0.1.0) |
| State | TypedDict (AgentState, VerificationResult, ThreatCheckResult, ExecutionResult) |
| Output | Structured JSON via response_format |
| Config | python-dotenv, shared config.py |

---

## Where it fits

This is the fifth of five agents in the multi-agent pipeline:

1. **Planner** breaks the task into steps and defines security requirements
2. **Threat Modeller** identifies relevant CWEs and live CVEs using RAG and NIST NVD
3. **Code Generator** writes code that follows the plan and implements every mitigation
4. **Code Reviewer** runs Bandit and GPT-4o review, produces a findings list with suggested fixes
5. **Verifier** (this agent) gives the final independent verdict using Bandit, sandbox, and RAG

The human participant reviews and approves, revises, or overrides the output at every stage. The experiment will measure whether this structured approach produces less vulnerable code than the single-agent baseline that receives no plan, no threat model, and no structured review.

---

## Research context

This project is part of an MSc dissertation at the University of Exeter (COMM514). It is a controlled experiment, not a production tool. Participants are computer science and software engineering students. All sessions are anonymised.

The Verifier is where the pipeline closes. The Code Reviewer found problems and suggested fixes. The Verifier asks a different question: after everything the pipeline did, did the code end up correct? That distinction matters for the experiment. A PASS from the Verifier is the thing being measured, not a PASS from the Reviewer.