"""
backend/utils.py
----------------
Shared helpers for route handlers.
"""

import json


def make_config(thread_id: str) -> dict:
    return {"configurable": {"thread_id": thread_id}}


def serialize_state(state: dict) -> dict:
    """
    Convert an AgentState dict to a JSON-safe dict.

    AgentState contains datetime strings and nested TypedDicts: all are
    JSON-serialisable via default=str as a safety net for any edge cases.
    """
    return json.loads(json.dumps(state, default=str))
