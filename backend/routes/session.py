"""
backend/routes/session.py
--------------------------
Multi-agent pipeline lifecycle endpoints.

POST /session/start             â€” initialise state, run Planner, pause
GET  /session/{thread_id}       â€” get current state snapshot
POST /session/{thread_id}/resume â€” apply a human decision and resume graph

The thread_id returned from /start is the stable handle for all subsequent
calls. The LangGraph MemorySaver checkpointer keeps state in memory for the
duration of the server process.
"""

from fastapi import APIRouter, HTTPException

from models import (
    ResumeRequest,
    ReviseCodeRequest,
    StartSessionRequest,
    StartSessionResponse,
    StateResponse,
)
from routes.tasks import _TASK_MAP
from utils import make_config, serialize_state

router = APIRouter()


@router.post("/start", response_model=StartSessionResponse)
async def start_session(req: StartSessionRequest):
    from multiagent.graph import get_current_state
    from multiagent.graph import start_session as _start
    from routes.participants import _load_participants

    if req.participant_id not in _load_participants():
        raise HTTPException(
            status_code=403,
            detail="Invalid participant ID. Please check your study link.",
        )

    task = _TASK_MAP.get(req.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id!r} not found")

    try:
        config = await _start(
            participant_id=req.participant_id,
            task=task.text,
            task_id=req.task_id,
            task_order=req.task_order,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Session start failed: {exc}")

    thread_id = config["configurable"]["thread_id"]
    state = get_current_state(config)
    return StartSessionResponse(thread_id=thread_id, state=serialize_state(state))


@router.get("/{thread_id}", response_model=StateResponse)
def get_state(thread_id: str):
    from multiagent.graph import get_current_state

    config = make_config(thread_id)
    try:
        state = get_current_state(config)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Session not found: {exc}")
    return StateResponse(state=serialize_state(state))


@router.post("/{thread_id}/revise", response_model=StateResponse)
async def revise_code(thread_id: str, req: ReviseCodeRequest):
    """
    Rewind to code_generator and re-run Code Reviewer with updated code.

    Called when the participant wants to fix their code after seeing review
    findings. Rewinds the LangGraph checkpoint to code_generator's output slot,
    updates user_code, clears the previous review results, then resumes so
    code_reviewer runs again and pauses at the same HITL interrupt.
    """
    from multiagent.graph import get_current_state, graph
    from utils import make_config, serialize_state

    config = make_config(thread_id)
    try:
        graph.update_state(
            config,
            {
                "user_code": req.user_code,
                "review_findings": None,
                "bandit_findings_review": None,
                "review_decision": None,
            },
            as_node="code_generator",
        )
        await graph.ainvoke(None, config=config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Revision failed: {exc}")

    state = get_current_state(config)
    return StateResponse(state=serialize_state(state))


@router.post("/{thread_id}/resume", response_model=StateResponse)
async def resume_session(thread_id: str, req: ResumeRequest):
    from multiagent.graph import get_current_state
    from multiagent.graph import resume_session as _resume

    config = make_config(thread_id)
    try:
        await _resume(config, req.state_update)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Resume failed: {exc}")

    state = get_current_state(config)
    return StateResponse(state=serialize_state(state))
