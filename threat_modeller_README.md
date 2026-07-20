# Threat Modeller Agent

**MSc Research Project · University of Exeter · COMM514**

![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4o-412991?style=flat&logo=openai&logoColor=white)
![LangGraph](https://img.shields.io/badge/LangGraph-Node-1C3C3C?style=flat&logo=langchain&logoColor=white)
![RAG](https://img.shields.io/badge/RAG-ChromaDB-FF6F00?style=flat&logo=databricks&logoColor=white)
![MCP](https://img.shields.io/badge/MCP-NIST%20NVD-D32F2F?style=flat)
![Async](https://img.shields.io/badge/Python-Async-3776AB?style=flat&logo=python&logoColor=white)
![Temp](https://img.shields.io/badge/Temperature-0.2-F97316?style=flat)
![Output](https://img.shields.io/badge/Output-Structured%20JSON-6366F1?style=flat)
![Research](https://img.shields.io/badge/University%20of%20Exeter-MSc%20Research-003c71?style=flat)

The second agent in a five-stage multi-agent pipeline for secure code generation. Before any code is written, the Threat Modeller identifies exactly which vulnerabilities are relevant to the task at hand, pulling from two live sources: a local RAG pipeline over the MITRE CWE Top 25 corpus, and real CVE data from the NIST National Vulnerability Database via MCP. The result is a structured threat model grounded in both established weakness taxonomy and recent real-world exploits.

This is part of a controlled experiment comparing a single-agent AI baseline against a human-orchestrated multi-agent system for secure code generation.

---

## Architecture

![Threat Modeller architecture](screenshots/threatmodellerarchitecture.PNG)

The Threat Modeller takes the coding task and the Planner's output (scope and security requirements) and runs two parallel intelligence pipelines before synthesising anything.

The RAG pipeline rewrites the task into security-domain search terms, queries a local ChromaDB vector store of the MITRE CWE Top 25, retrieves the top 10 candidates by cosine similarity, and uses GPT-4o to re-rank them down to the 3 most relevant weaknesses. The top-ranked CWE's short name then becomes the keyword for a live NIST NVD API call via MCP, which returns the 3 most recent CVEs mapped to that weakness with CVSS scores and severity ratings.

GPT-4o synthesises both sources alongside the task and plan to produce a list of ThreatEntry objects, each with a task-specific description and an actionable mitigation.

```
Coding Task + Planner Output
           |
    run_threat_modeller(state)
           |
   RAG Pipeline         MCP Tool (NIST NVD)
   Query Rewrite  --->  top CWE as keyword
   ChromaDB             live CVE lookup
   LLM Re-rank          3 recent CVEs
   Top 3 CWEs
           |
        GPT-4o
     temp: 0.2, JSON mode
           |
     ThreatEntry List
     cwe_id · severity
     task-specific description
     actionable mitigation
           |
    Code Generator (next agent)
```

The threat model is not a generic checklist. Every entry is written specifically for the coding task. "Sanitise all inputs" is not an output of this agent. "Use parameterised queries with sqlite3's `?` placeholder syntax to prevent SQL injection in the login function" is.

---

## What it produces

![Threat Modeller terminal output](screenshots/threatmodellerresponse.PNG)

For the task "Write a Python function that checks a username and password against a SQLite database", the Threat Modeller returned:

- **CWE-89 (SQL Injection) — Critical**: task-specific description of the injection vector in a login function, mitigation calling out parameterised queries with explicit sqlite3 syntax
- **CWE-20 (Improper Input Validation) — Medium**: description focused on unvalidated username and password fields before the database query, mitigation specifying length limits and character allowlists

Both entries came from real CWEs ranked against the task. Both mitigations are actionable. The Code Generator reads this list directly and implements accordingly.

---

## Inside the code

![Threat Modeller code](screenshots/threat_modeller.PNG)

The RAG pipeline uses a query rewrite step before hitting ChromaDB. Instead of embedding the raw task, GPT-4o first expands it into security-domain terms and relevant vulnerability categories. This closes the vocabulary gap between how tasks are phrased and how CWE entries are written in the corpus.

The NVD keyword comes from the top-ranked CWE's short name rather than a separate GPT-4o call. Once the re-ranker picks the most relevant CWE, its `short_name` field is passed directly to the `search_nvd` MCP tool. This keeps the lookup grounded in the RAG result without adding API cost.

The MCP tool calls run through a `MultiServerMCPClient` using stdio transport. The NVD server is a local Python MCP server that wraps the NIST REST API v2. One technical detail worth noting: MCP stdio servers wire their stdin to the communication pipe, so any subprocess they spawn has to be given `stdin=DEVNULL` explicitly or it will hang waiting for input on the MCP pipe. Both the Bandit and NVD servers handle this.

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

**3. Ingest the CWE corpus into ChromaDB**

```bash
python -m rag.ingest
```

This only needs to run once. It embeds the MITRE CWE Top 25 entries using `text-embedding-3-small` and stores them in a local ChromaDB collection.

**4. Run the standalone test**

```bash
python -m multiagent.agents.threat_modeller --test
```

This runs the full pipeline against a sample login task and prints the structured threat model including CWE IDs, severity ratings, task-specific descriptions, and mitigations.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| LLM | GPT-4o via OpenAI API |
| Orchestration | LangGraph (async node) |
| RAG | ChromaDB + text-embedding-3-small |
| Corpus | MITRE CWE Top 25 (2025) |
| Live CVE data | NIST NVD REST API v2 via MCP |
| MCP transport | stdio (langchain-mcp-adapters 0.1.0) |
| State | TypedDict (AgentState, ThreatEntry) |
| Output | Structured JSON via response_format |
| Config | python-dotenv, shared config.py |

---

## Where it fits

This is the second of five agents in the multi-agent pipeline:

1. **Planner** breaks the task into implementation steps and defines security requirements
2. **Threat Modeller** (this agent) identifies relevant CWEs and real CVEs specific to the task
3. **Code Generator** writes code informed by the plan and threat model
4. **Code Reviewer** runs Bandit static analysis via MCP and critiques the output
5. **Verifier** validates the final code against the original threat model

The human participant reviews and approves, revises, or overrides the output at every stage. The full system uses ChromaDB for vector search, LangGraph for orchestration, and MCP tool servers for Bandit, NIST NVD, and sandboxed code execution.

The experiment will measure whether this structured approach produces less vulnerable code than the single-agent baseline.

---

## Research context

This project is part of an MSc dissertation at the University of Exeter (COMM514). It is a controlled experiment, not a production tool. Participants are computer science and software engineering students. All sessions are anonymised.

The Threat Modeller is the part of the pipeline that separates security theatre from security engineering. Generic advice is easy to generate. Vulnerability-specific, task-grounded analysis backed by real CVE data is what this agent is built to produce.
