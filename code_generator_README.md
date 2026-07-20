# Code Generator Agent

**MSc Research Project · University of Exeter · COMM514**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Node-1C3C3C?style=flat&logo=langchain&logoColor=white)
![Async](https://img.shields.io/badge/Python-Async-3776AB?style=flat&logo=python&logoColor=white)
![Temp](https://img.shields.io/badge/Temperature-0.2-F97316?style=flat)
![No RAG](https://img.shields.io/badge/RAG-None-lightgrey?style=flat)
![No MCP](https://img.shields.io/badge/MCP-None-lightgrey?style=flat)
![Output](https://img.shields.io/badge/Output-Structured%20JSON-6366F1?style=flat)
![Research](https://img.shields.io/badge/University%20of%20Exeter-MSc%20Research-003c71?style=flat)

The third agent in a five-stage multi-agent pipeline for secure code generation. By the time the Code Generator runs, the Planner has already broken the task into ordered steps with explicit security requirements, and the Threat Modeller has identified the specific CWEs that apply to this task along with concrete mitigations. The Code Generator's job is to take all of that and produce code that actually satisfies it.

No RAG. No MCP. That is a deliberate design decision. The intelligence-gathering work is done. This agent acts on it.

This is part of a controlled experiment comparing a single-agent AI baseline against a human-orchestrated multi-agent system for secure code generation.

---

## Architecture

![Code Generator architecture](screenshots/code_generator%20architecture.PNG)

Three inputs feed into the Code Generator: the raw coding task, the Planner's structured output (scope, implementation steps, security requirements), and the Threat Modeller's threat model (CWE-mapped entries with task-specific mitigations and severity ratings).

Before the prompt is assembled, two helper functions convert the TypedDict inputs into labelled plain text blocks. Structured plain text with clear section headers gives GPT-4o better anchors than raw JSON in the user message. The assembled prompt then goes to GPT-4o with `response_format=json_object` enforcing structured output.

```
Coding Task  +  Planner Output  +  Threat Model
                      |
               Prompt Assembly
         TASK + formatted plan + formatted threats
                      |
                   GPT-4o
            temp: 0.2  ·  JSON mode
            no RAG  ·  no MCP
                      |
          ┌───────────┴───────────┐
    generated_code          code_explanation
    complete Python          maps mitigations
    function                 back to CWE IDs
                      |
              Code Reviewer
```

---

## What it produces

![Code Generator terminal output](screenshots/code_generator%20response.PNG)

For the task "Write a Python function that checks a username and password against a SQLite database", the Code Generator produced a function that:

- Validates input type and length before touching the database
- Uses sqlite3 parameterised queries with the `?` placeholder throughout
- Returns a generic `False` on failure without revealing whether the username or password was wrong
- Verifies passwords with `bcrypt.checkpw()` with correct byte encoding on both sides
- Wraps the connection in a `finally` block so it closes even if an exception is thrown mid-query

None of those decisions came from the Code Generator inventing them. They came from the plan steps and threat mitigations that arrived in state from earlier agents. The Code Generator followed instructions. That is exactly what it is supposed to do.

The explanation field maps each mitigation back to its CWE ID with the specific mechanism used, not a generic statement. That output goes into the evaluation log and is one of the things being measured in the experiment.

---

## Inside the code

![Code Generator source code](screenshots/code%20generator%20file%20snipet.PNG)

The `run_code_generator()` function is an async LangGraph node. It reads three fields from shared state, formats them using the two helper functions, assembles a user message, and calls GPT-4o via the OpenAI SDK with `response_format={"type": "json_object"}` to guarantee parseable output every time.

The return value is a partial state dict — only the fields this agent touches. LangGraph merges it back into the full pipeline state automatically. Setting `current_stage: "code_review"` tells the graph which node runs next.

The `except` block catches any failure and returns the same dict shape with `current_stage: "error"` so the graph routes cleanly to error handling rather than crashing mid-pipeline.

The two formatter functions are worth looking at. `_format_plan()` numbers the implementation steps and bullet-points the requirements. `_format_threats()` turns each ThreatEntry into a labelled block with the CWE ID, severity, what the threat is, and what to do about it. The labels give GPT-4o clear anchors for what each piece of information means and what it is supposed to do with it.

---

## How to run it

**1. Clone the repo and install dependencies**

```bash
pip install openai python-dotenv langchain-mcp-adapters chromadb bcrypt
```

**2. Add your OpenAI API key**

Create a `.env` file in the project root:

```
OPENAI_API_KEY=your-key-here
```

**3. Run the standalone test**

```bash
python -m multiagent.agents.code_generator --test
```

This runs the Code Generator against a pre-built plan and threat model for a login function task and prints the full generated code along with the security explanation.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| LLM | GPT-4o via OpenAI API |
| Orchestration | LangGraph (async node) |
| State | TypedDict (AgentState, PlannerOutput, ThreatEntry) |
| Output | Structured JSON via response_format |
| Config | python-dotenv, shared config.py |
| RAG | None |
| MCP | None |

---

## Where it fits

This is the third of five agents in the multi-agent pipeline:

1. **Planner** breaks the task into steps and defines security requirements before any code exists
2. **Threat Modeller** identifies relevant CWEs and live CVEs specific to the task using RAG and NIST NVD
3. **Code Generator** (this agent) writes code that follows the plan and implements every mitigation
4. **Code Reviewer** runs Bandit static analysis via MCP and produces structured security findings
5. **Verifier** validates the final code against the original threat model using Bandit and a sandbox

The human participant reviews and approves, revises, or overrides the output at every stage. The full system uses ChromaDB for vector search, LangGraph for orchestration, and MCP tool servers for Bandit, NIST NVD, and sandboxed code execution.

The experiment will measure whether this structured approach produces less vulnerable code than the single-agent baseline that receives no plan, no threat model, and no structured review.

---

## Research context

This project is part of an MSc dissertation at the University of Exeter (COMM514). It is a controlled experiment, not a production tool. Participants are computer science and software engineering students. All sessions are anonymised.

The Code Generator is the agent where the earlier work either pays off or it does not. If the Planner produced specific steps and the Threat Modeller produced task-grounded mitigations, the Code Generator has everything it needs. If either of those failed to be specific enough, the Code Generator has nothing concrete to act on. The quality of this agent's output is a direct measure of the quality of the two agents before it.
