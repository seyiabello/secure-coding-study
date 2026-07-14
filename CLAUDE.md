# CLAUDE.md — Secure Coding Study

MSc Research Project (COMM514), University of Exeter.
Controlled experiment comparing a single-agent AI baseline against a human-orchestrated multi-agent system for secure code generation.

---

## Project structure

```
secure-coding-study/
├── backend/                ← ALL Python code lives here
│   ├── main.py             ← FastAPI app entry point
│   ├── models.py           ← Pydantic request/response models
│   ├── routes/             ← API route handlers
│   ├── utils.py
│   ├── config.py           ← single OpenAI client, MODEL, TEMPERATURE
│   ├── mcp_client.py
│   ├── multiagent/         ← LangGraph pipeline + 5 agents
│   ├── rag/                ← ChromaDB + retriever
│   ├── mcp_servers/        ← Bandit, NVD, Sandbox MCP servers
│   ├── baseline/           ← single-agent baseline
│   └── evaluation/         ← scoring + stats
├── frontend/               ← Next.js participant UI (to be built)
├── tests/                  ← pytest test suite
├── logs/                   ← JSONL session logs (output, not code)
└── chroma_db/              ← ChromaDB vector store (output, not code)
```

## Run commands

```powershell
# Backend (run from backend/ directory)
cd backend
uvicorn main:app --reload --port 8000

# Backend pipeline test (end-to-end, from project root)
.\venv\Scripts\python.exe -m backend.multiagent.graph --test   # TODO: update graph.py __main__ if needed
# OR from backend/:
# python -m multiagent.graph --test

# Tests (from project root)
$env:PYTHONPATH = "backend"; .\venv\Scripts\python.exe -m pytest tests/ -v

# Frontend (from frontend/ directory)
cd frontend
npm run dev
```

---

## Tech stack

- Python, OpenAI API (GPT-4o), LangGraph, FastAPI, uvicorn
- RAG: ChromaDB + OpenAI `text-embedding-3-small` + Advanced RAG pipeline
- MCP: `langchain-mcp-adapters`, `MultiServerMCPClient`, stdio transport
- Frontend: Next.js 15, React 19, TypeScript, Tailwind CSS, Monaco Editor
- Logging: JSONL. Stats: scipy.

---

## What is done

- `backend/baseline/agent.py` — single-agent baseline, direct OpenAI SDK, fully working and tested
- `backend/baseline/prompts.py` — minimal system prompt, no security instructions
- `backend/config.py` — single shared OpenAI client, exports `client`, `MODEL`, `TEMPERATURE`
- `backend/multiagent/` — full LangGraph pipeline (5 agents, RAG, MCP, HITL redesign)
- `backend/rag/` — Advanced RAG pipeline (ChromaDB, reranking, query rewriting)
- `backend/mcp_servers/` — Bandit, NVD, Sandbox servers (tested standalone)
- `backend/evaluation/` — Bandit scoring + Mann-Whitney U / Wilcoxon
- `backend/main.py` + `backend/routes/` — FastAPI REST API (all endpoints working)
- `tests/` — unit tests (conftest.py sets PYTHONPATH=backend automatically)
- `frontend/` — fresh directory, Next.js UI to be built here

---

## Build order (reference — all backend items complete)

1. `backend/rag/cwe_corpus/cwe_top25.json`
2. `backend/rag/ingest.py`
3. `backend/rag/retriever.py`
4. `backend/multiagent/state.py`
5. `backend/mcp_servers/` (bandit, nist_nvd, sandbox)
6. `backend/mcp_client.py`
7. `backend/multiagent/agents/` (planner → threat_modeller → code_generator → code_reviewer → verifier)
8. `backend/multiagent/graph.py`
9. `backend/main.py` + `backend/routes/`
10. `frontend/` — Next.js UI (next task)

---

## Hard rules — never break

- Baseline system prompt must stay minimal. No security instructions. No structured review.
- Temperature 0.2 everywhere. Variation between conditions must come from architecture.
- One OpenAI client in `config.py`. Never instantiate inside agent files. Never hardcode the API key.
- Log schema identical across both conditions except the `condition` field.
- All core functions must be importable. CLI wrappers in `if __name__ == "__main__"` only.
- No LangChain in the baseline. Direct OpenAI SDK only.
- `state.py` before any agent.
- Test each MCP server standalone before connecting via MultiServerMCPClient.
- Test RAG retrieval quality before wiring into agents.
- Each agent outputs structured JSON. Define schema before writing the prompt.
- Code Reviewer and Verifier run Bandit independently — must not share results.

---

## Skills
For any frontend or UI work, read /mnt/skills/public/frontend-design/SKILL.md before writing code.

---

## Agent tooling summary

| Agent | RAG | MCP |
|---|---|---|
| Planner | No | No |
| Threat Modeller | Yes (CWE corpus) | Yes (NIST NVD) |
| Code Generator | No | No |
| Code Reviewer | No | Yes (Bandit) |
| Verifier | Yes (CWE corpus) | Yes (Bandit + Sandbox) |
