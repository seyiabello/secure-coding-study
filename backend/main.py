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
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from routes import baseline, hints, participants, session, tasks

load_dotenv()

app = FastAPI(
    title="Secure Coding Study API",
    version="0.1.0",
    description=(
        "Backend for COMM514 MSc research â€” baseline vs multi-agent secure code generation."
    ),
)

# Allow the Next.js dev server and production domain(s) to call the API.
# FRONTEND_ORIGIN accepts a comma-separated list so local + Vercel both work.
_origins = [
    o.strip()
    for o in os.environ.get(
        "FRONTEND_ORIGIN", "http://localhost:3000"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def _require_study_open():
    if os.environ.get("STUDY_OPEN", "true").lower() == "false":
        raise HTTPException(status_code=503, detail="The study is currently closed.")


app.include_router(tasks.router,        prefix="/tasks",        tags=["tasks"])
app.include_router(participants.router, prefix="/participants",  tags=["participants"])
app.include_router(
    baseline.router,
    prefix="/baseline",
    tags=["baseline"],
    dependencies=[Depends(_require_study_open)],
)
app.include_router(
    session.router,
    prefix="/session",
    tags=["session"],
    dependencies=[Depends(_require_study_open)],
)
app.include_router(
    hints.router,
    prefix="/session",
    tags=["hints"],
    dependencies=[Depends(_require_study_open)],
)


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
async def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/docs")
