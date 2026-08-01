"""
backend/routes/participants.py
-------------------------------
GET  /participants/validate/{pid}  - validate PID; returns status new/in_progress or complete
GET  /participants/resume/{pid}    - return how many tasks are done so session can resume
POST /participants/consent         - append consent record to consent_log.jsonl
GET  /participants/status          - researcher monitoring dashboard (API-key protected)
"""

import datetime
import json
import os
from collections import Counter
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from models import ConsentLogRequest, ParticipantRegisterRequest

router = APIRouter()

_PARTICIPANTS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "participants.json"
_CONSENT_LOG       = Path(__file__).resolve().parent.parent / "logs" / "consent_log.jsonl"
_BASELINE_LOG      = Path(__file__).resolve().parent.parent / "logs" / "baseline_sessions.jsonl"
_MULTIAGENT_LOG    = Path(__file__).resolve().parent.parent / "logs" / "multiagent_sessions.jsonl"

TOTAL_TASKS = 4


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_participants() -> dict[str, str]:
    """Read participants.json fresh on every call so new enrolments are visible immediately."""
    try:
        with open(_PARTICIPANTS_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_participants(data: dict[str, str]) -> None:
    """Write participants.json atomically via a temp-file rename."""
    _PARTICIPANTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PARTICIPANTS_FILE.with_suffix(".tmp")
    with open(tmp, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    os.replace(tmp, _PARTICIPANTS_FILE)


def _read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except FileNotFoundError:
        pass
    return records


def _has_consent(pid: str) -> bool:
    return any(r.get("participant_id") == pid for r in _read_jsonl(_CONSENT_LOG))


def _completed_task_ids(pid: str, condition: str) -> list[str]:
    """Return task_ids already completed by this participant in their condition log."""
    log = _BASELINE_LOG if condition == "baseline" else _MULTIAGENT_LOG
    return [
        r.get("task_id", "")
        for r in _read_jsonl(log)
        if r.get("participant_id") == pid
    ]


def _is_session_complete(pid: str, condition: str) -> bool:
    return len(_completed_task_ids(pid, condition)) >= TOTAL_TASKS


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register")
def register_participant(req: ParticipantRegisterRequest):
    """
    Called by the Google Apps Script immediately after assigning a participant ID.
    Adds the participant to participants.json so their study link works instantly.
    Idempotent: re-registering with the same pid and condition is a no-op.
    """
    expected_key = os.environ.get("PARTICIPANT_REGISTER_KEY", "")
    if not expected_key or req.secret != expected_key:
        raise HTTPException(status_code=401, detail="Unauthorised.")

    if req.condition not in ("baseline", "multiagent"):
        raise HTTPException(
            status_code=422,
            detail=f"Invalid condition {req.condition!r}. Must be 'baseline' or 'multiagent'.",
        )

    if not req.participant_id.strip():
        raise HTTPException(status_code=422, detail="participant_id must not be empty.")

    participants = _load_participants()
    participants[req.participant_id] = req.condition
    _save_participants(participants)

    return {"ok": True, "participant_id": req.participant_id, "condition": req.condition}


@router.get("/validate/{pid}")
def validate_participant(pid: str):
    participants = _load_participants()
    if pid not in participants:
        return {"valid": False, "reason": "not_found"}

    condition = participants[pid]

    if _is_session_complete(pid, condition):
        return {"valid": False, "reason": "complete"}

    if _has_consent(pid):
        completed = _completed_task_ids(pid, condition)
        return {
            "valid": True,
            "condition": condition,
            "status": "in_progress",
            "tasks_completed": len(completed),
        }

    return {"valid": True, "condition": condition, "status": "new"}


@router.get("/resume/{pid}")
def resume_participant(pid: str):
    participants = _load_participants()
    if pid not in participants:
        raise HTTPException(status_code=404, detail="Participant not found.")
    condition = participants[pid]
    completed = _completed_task_ids(pid, condition)
    return {
        "condition": condition,
        "tasks_completed": len(completed),
        "completed_task_ids": completed,
    }


@router.post("/consent")
async def log_consent(req: ConsentLogRequest):
    _CONSENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "participant_id": req.participant_id,
        "timestamp": req.timestamp,
        "all_items_confirmed": req.all_items_confirmed,
        "logged_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    try:
        with open(_CONSENT_LOG, "a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception:
        pass  # logging failure must never block a participant
    return {"ok": True}


@router.get("/status")
def study_status(request: Request):
    """Researcher monitoring endpoint — requires X-Api-Key header if MONITORING_API_KEY is set."""
    api_key = os.environ.get("MONITORING_API_KEY", "")
    if api_key and request.headers.get("x-api-key") != api_key:
        raise HTTPException(status_code=401, detail="Unauthorised.")

    participants = _load_participants()
    total_assigned      = len(participants)
    baseline_assigned   = sum(1 for c in participants.values() if c == "baseline")
    multiagent_assigned = sum(1 for c in participants.values() if c == "multiagent")

    consent_pids = {r["participant_id"] for r in _read_jsonl(_CONSENT_LOG)}
    consent_given = len(consent_pids)

    baseline_counts   = Counter(r["participant_id"] for r in _read_jsonl(_BASELINE_LOG))
    multiagent_counts = Counter(r["participant_id"] for r in _read_jsonl(_MULTIAGENT_LOG))

    baseline_completed   = sum(1 for n in baseline_counts.values()   if n >= TOTAL_TASKS)
    multiagent_completed = sum(1 for n in multiagent_counts.values() if n >= TOTAL_TASKS)
    sessions_completed   = baseline_completed + multiagent_completed

    complete_pids = (
        {p for p, n in baseline_counts.items()   if n >= TOTAL_TASKS}
        | {p for p, n in multiagent_counts.items() if n >= TOTAL_TASKS}
    )
    sessions_in_progress = len(consent_pids - complete_pids)

    return {
        "total_assigned":       total_assigned,
        "baseline_assigned":    baseline_assigned,
        "multiagent_assigned":  multiagent_assigned,
        "consent_given":        consent_given,
        "sessions_completed":   sessions_completed,
        "baseline_completed":   baseline_completed,
        "multiagent_completed": multiagent_completed,
        "sessions_in_progress": sessions_in_progress,
    }
