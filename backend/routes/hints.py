"""
backend/routes/hints.py
------------------------
Code Generator HITL endpoints: all scoped under /session/{thread_id}.

POST /session/{thread_id}/hint: request a per-step hint
POST /session/{thread_id}/next-hint: adaptive "what should I do next?" (reads code)
POST /session/{thread_id}/security-hint: whole-code real-time security feedback
GET  /session/{thread_id}/step-caps: per-step hint depth caps (computed once, cached)
POST /session/{thread_id}/finalize: submit code + metrics, resume to Code Reviewer

The step-caps endpoint runs the step classifier (one GPT-4o call) on first
request and stores the result in graph state so subsequent calls are instant.
"""

from fastapi import APIRouter, HTTPException

from models import (
    FinalizeCodeRequest,
    HintRequest,
    NextHintRequest,
    SecurityHintRequest,
    StateResponse,
)
from utils import make_config, serialize_state

router = APIRouter()

# Valid hint levels in ascending order of reveal depth
_VALID_LEVELS = ("direction", "pseudocode", "partial", "full")
_LEVEL_DEPTH  = {"direction": 1, "pseudocode": 2, "partial": 3, "full": 4}


@router.post("/{thread_id}/hint")
async def get_hint(thread_id: str, req: HintRequest):
    """
    Returns a per-step hint at the requested level.

    Enforces step_hint_caps: if the requested level exceeds the cap for this
    step, returns a 403 with the maximum allowed level in the detail.
    """
    from multiagent.agents.code_generator import get_step_hint as _get_step_hint
    from multiagent.graph import get_current_state

    if req.level not in _VALID_LEVELS:
        raise HTTPException(status_code=400, detail=f"Invalid level '{req.level}'.")

    config = make_config(thread_id)
    state  = get_current_state(config)

    # Enforce cap if available
    caps = state.get("step_hint_caps") or []
    cap_entry = next((c for c in caps if c["step_index"] == req.step_index), None)
    if cap_entry:
        max_depth     = _LEVEL_DEPTH[cap_entry["max_level"]]
        request_depth = _LEVEL_DEPTH[req.level]
        if request_depth > max_depth:
            raise HTTPException(
                status_code=403,
                detail=(
                    f"Step {req.step_index} is capped at '{cap_entry['max_level']}'. "
                    f"Requested '{req.level}' is not available for this step."
                ),
            )

    return await _get_step_hint(state, req.step_index, req.level)


@router.post("/{thread_id}/next-hint")
async def get_next_hint(thread_id: str, req: NextHintRequest):
    """
    Adaptive hint: reads the participant's current code and suggests what to do next.

    Identifies which plan steps are done/missing/wrong and returns a focused
    next-step suggestion. Does not reveal implementation: only direction.
    """
    from multiagent.agents.code_generator import get_next_hint as _get_next_hint
    from multiagent.graph import get_current_state

    config = make_config(thread_id)
    state  = get_current_state(config)
    return await _get_next_hint(state, req.code_so_far)


@router.post("/{thread_id}/security-hint")
async def get_security_hint(thread_id: str, req: SecurityHintRequest):
    """Whole-code security-focused hint: flags the single most pressing issue."""
    from multiagent.agents.code_generator import get_security_hint as _get_security_hint
    from multiagent.graph import get_current_state

    config = make_config(thread_id)
    state  = get_current_state(config)
    return await _get_security_hint(state, req.code_so_far)


@router.get("/{thread_id}/step-caps")
async def get_step_caps(thread_id: str):
    """
    Returns per-step hint depth caps, computing and caching them on first call.

    On first request (step_hint_caps is None in state), runs the step classifier
    (one GPT-4o call) and stores the result in graph state. Subsequent requests
    return the cached result instantly.

    Returns
    -------
    { "step_caps": [{ "step_index": int, "max_level": str, "reason": str }] }
    """
    from multiagent.graph import get_current_state
    from multiagent.graph import graph as _graph
    from multiagent.step_classifier import classify_steps

    config = make_config(thread_id)
    state  = get_current_state(config)

    caps = state.get("step_hint_caps")

    if caps is None:
        plan    = state.get("plan")
        threats = state.get("threats") or []

        if not plan:
            raise HTTPException(status_code=400, detail="Plan not yet available.")

        caps = classify_steps(plan, threats)
        _graph.update_state(config, {"step_hint_caps": caps})

    return {"step_caps": caps}


@router.post("/{thread_id}/finalize", response_model=StateResponse)
async def finalize_code(thread_id: str, req: FinalizeCodeRequest):
    """
    Submits the participant's code and HITL metrics, then resumes the pipeline
    → Code Reviewer runs → graph pauses at code_review stage.
    """
    from multiagent.agents.code_generator import finalize_code as _finalize
    from multiagent.graph import get_current_state
    from multiagent.graph import graph as _graph
    from multiagent.graph import resume_session as _resume

    config = make_config(thread_id)
    state  = get_current_state(config)

    updates = _finalize(
        state,
        user_code=req.user_code,
        annotations=req.annotations,
        confidence_rating=req.confidence_rating,
        hints_requested=req.hints_requested,
        time_in_coding_seconds=req.time_in_coding_seconds,
    )

    if req.pre_review_prediction is not None:
        updates["pre_review_prediction"] = req.pre_review_prediction

    try:
        await _resume(config, updates)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Code review failed: {exc}")

    new_state = get_current_state(config)

    # Calibration score: fraction of predicted CWEs confirmed by Code Reviewer
    predicted = set(req.pre_review_prediction or [])
    if predicted:
        actual_cwes = {
            f.get("cwe_id")
            for f in (new_state.get("review_findings") or [])
            if f.get("cwe_id")
        }
        accuracy = round(len(predicted & actual_cwes) / len(predicted), 3)
        _graph.update_state(config, {"prediction_accuracy": accuracy})
        new_state = get_current_state(config)

    return StateResponse(state=serialize_state(new_state))
