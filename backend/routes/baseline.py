"""
backend/routes/baseline.py
---------------------------
POST /baseline/run

Runs the baseline agent on the given task, logs the session, and returns
the generated code. One call does everything â€” no state to manage.
"""

import asyncio
import datetime

from fastapi import APIRouter, HTTPException

from models import BaselineRunRequest, BaselineRunResponse
from routes.tasks import _TASK_MAP

router = APIRouter()


@router.post("/run", response_model=BaselineRunResponse)
async def run_baseline(req: BaselineRunRequest):
    from baseline.agent import log_session, run_baseline as _generate
    from routes.participants import _load_participants

    if req.participant_id not in _load_participants():
        raise HTTPException(
            status_code=403,
            detail="Invalid participant ID. Please check your study link.",
        )

    task = _TASK_MAP.get(req.task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task {req.task_id!r} not found")

    start = datetime.datetime.now(datetime.timezone.utc)

    try:
        # run_baseline is synchronous (direct OpenAI SDK call).
        # asyncio.to_thread offloads it to a thread pool so the event loop
        # is not blocked while waiting for the API response.
        response = await asyncio.to_thread(_generate, task.text)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Generation failed: {exc}")

    duration = (datetime.datetime.now(datetime.timezone.utc) - start).total_seconds()

    logged = False
    try:
        log_session(
            participant_id=req.participant_id,
            task=task.text,
            response=response,
            duration_seconds=round(duration, 3),
            task_id=req.task_id,
            task_order=req.task_order,
            participant_notes=req.participant_notes,
        )
        logged = True
    except Exception:
        pass  # logging failure must never break the participant's flow

    return BaselineRunResponse(
        response=response,
        duration_seconds=round(duration, 3),
        logged=logged,
    )
