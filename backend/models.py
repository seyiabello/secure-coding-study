"""
backend/models.py
-----------------
Pydantic request and response schemas for the FastAPI backend.

Keep these flat — the frontend sees these shapes, not the internal
AgentState TypedDicts which are richer but not serialisation-friendly.
"""

from pydantic import BaseModel


# ── Tasks ──────────────────────────────────────────────────────────────────────

class Task(BaseModel):
    task_id: str
    text: str


# ── Baseline ───────────────────────────────────────────────────────────────────

class BaselineRunRequest(BaseModel):
    participant_id: str
    task_id: str
    task_order: int
    participant_notes: str | None = None


class BaselineRunResponse(BaseModel):
    response: str
    duration_seconds: float
    logged: bool


# ── Multi-agent session lifecycle ──────────────────────────────────────────────

class StartSessionRequest(BaseModel):
    participant_id: str
    task_id: str
    task_order: int


class StartSessionResponse(BaseModel):
    thread_id: str
    state: dict


class ResumeRequest(BaseModel):
    state_update: dict


class StateResponse(BaseModel):
    state: dict


# ── Code Generator HITL ────────────────────────────────────────────────────────

class HintRequest(BaseModel):
    step_index: int   # 0-indexed plan step
    level: str        # "direction" | "pseudocode" | "partial" | "full"


class NextHintRequest(BaseModel):
    code_so_far: str  # participant's current code — adaptive next-step suggestion


class SecurityHintRequest(BaseModel):
    code_so_far: str  # whole-code security-focused pass


class FinalizeCodeRequest(BaseModel):
    user_code: str
    annotations: dict                     # CodingAnnotations
    confidence_rating: int                # 1 – 5
    hints_requested: list[dict]           # list of HintRecord (step_index, level, timestamp)
    time_in_coding_seconds: float
    pre_review_prediction: list[str] | None = None  # predicted CWE IDs


class ReviseCodeRequest(BaseModel):
    user_code: str
