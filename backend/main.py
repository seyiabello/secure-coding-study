"""
backend/main.py
---------------
FastAPI application for the Secure Coding Study.

Wraps the existing LangGraph multi-agent pipeline and baseline agent
behind a REST API so the Next.js frontend can drive both experiment
conditions.

Run (from project root):
    uvicorn backend.main:app --reload --port 8000

Environment variables:
    FRONTEND_ORIGIN  â€” allowed CORS origin (default: http://localhost:3000)
    OPENAI_API_KEY   â€” required; set in .env at project root
"""

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routes import baseline, hints, session, tasks

load_dotenv()

app = FastAPI(
    title="Secure Coding Study API",
    version="0.1.0",
    description=(
        "Backend for COMM514 MSc research â€” baseline vs multi-agent secure code generation."
    ),
)

# Allow the Next.js dev server (and production domain) to call the API.
# FRONTEND_ORIGIN can be overridden in production via environment variable.
_origins = [
    os.environ.get("FRONTEND_ORIGIN", "http://localhost:3000"),
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router,    prefix="/tasks",    tags=["tasks"])
app.include_router(baseline.router, prefix="/baseline", tags=["baseline"])
app.include_router(session.router,  prefix="/session",  tags=["session"])
app.include_router(hints.router,    prefix="/session",  tags=["hints"])


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")
