"""
tests/test_agents.py
--------------------
Unit tests for multi-agent pipeline agents.

All tests are offline — no real API calls, no real LangGraph execution.
OpenAI calls are patched with unittest.mock so tests run without credentials
and without incurring API costs.

Run:
    pytest tests/test_agents.py -v
"""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from multiagent.agents.code_generator import (
    finalize_code,
    get_hint,
    get_security_hint,
    run_code_generator,
)
from multiagent.state import (
    CodingAnnotations,
    HintRecord,
    create_initial_state,
)


# =============================================================================
# Fixtures
# =============================================================================

def _make_state(task: str = "Write a Python login function") -> dict:
    state = create_initial_state("TEST", task)
    state["plan"] = {
        "steps": [
            "Validate username and password inputs",
            "Query database with parameterised query",
            "Compare password hash with bcrypt",
            "Return True on match, False otherwise",
        ],
        "scope": "Single login function against SQLite. No sessions or registration.",
        "security_requirements": [
            "Use parameterised queries",
            "Compare passwords with bcrypt, not plaintext",
            "Validate input types and lengths",
        ],
    }
    state["threats"] = [
        {
            "cwe_id": "CWE-89",
            "name": "SQL Injection",
            "severity": "Critical",
            "description": "Concatenating username into SQL allows auth bypass.",
            "mitigation": "Use parameterised queries with ? placeholder.",
        },
        {
            "cwe_id": "CWE-20",
            "name": "Improper Input Validation",
            "severity": "Medium",
            "description": "Unvalidated inputs can cause unexpected behaviour.",
            "mitigation": "Validate type and length before querying.",
        },
    ]
    return state


def _mock_openai_response(content: dict) -> MagicMock:
    """Returns a MagicMock that mimics an OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = json.dumps(content)
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# =============================================================================
# get_hint tests
# =============================================================================

class TestGetHint:

    @pytest.mark.anyio
    async def test_hint_level_1_returns_direction(self):
        state = _make_state()
        mock_resp = _mock_openai_response({
            "content": "Start by writing the validate_inputs function...",
            "security_note": "Validate length before touching the DB (CWE-20).",
        })
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_resp
            result = await get_hint(state, 1)

        assert result["level"] == 1
        assert result["hint_type"] == "direction"
        assert result["content"] == "Start by writing the validate_inputs function..."
        assert result["security_note"] == "Validate length before touching the DB (CWE-20)."
        assert result["error"] is None
        assert "timestamp" in result

    @pytest.mark.anyio
    async def test_hint_level_2_returns_pseudocode(self):
        state = _make_state()
        mock_resp = _mock_openai_response({
            "content": "# def verify(u, p):\n#   1. Validate inputs (CWE-20)",
            "security_note": "Parameterised query is the most critical step.",
        })
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_resp
            result = await get_hint(state, 2)

        assert result["level"] == 2
        assert result["hint_type"] == "pseudocode"
        assert result["error"] is None

    @pytest.mark.anyio
    async def test_hint_level_3_returns_partial_code(self):
        state = _make_state()
        mock_resp = _mock_openai_response({
            "content": "import sqlite3\n\ndef verify(u, p):\n    # TODO [CWE-20]: validate",
            "security_note": "Fill in all TODO sections — those are the security-critical parts.",
        })
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_resp
            result = await get_hint(state, 3)

        assert result["level"] == 3
        assert result["hint_type"] == "partial_code"
        assert "TODO" in result["content"]
        assert result["error"] is None

    @pytest.mark.anyio
    async def test_hint_level_4_returns_full_code(self):
        state = _make_state()
        full_code = "# [AI-GENERATED CODE]\nimport sqlite3\nimport bcrypt\n\ndef verify(u, p): ..."
        mock_resp = _mock_openai_response({
            "content": full_code,
            "security_note": "Parameterised query and bcrypt are implemented.",
        })
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_resp
            result = await get_hint(state, 4)

        assert result["level"] == 4
        assert result["hint_type"] == "full_code"
        assert "[AI-GENERATED CODE]" in result["content"]
        assert result["error"] is None

    @pytest.mark.anyio
    async def test_invalid_hint_level_returns_error(self):
        state = _make_state()
        result = await get_hint(state, 0)
        assert result["error"] is not None
        assert "Invalid hint level" in result["error"]

    @pytest.mark.anyio
    async def test_invalid_hint_level_5_returns_error(self):
        state = _make_state()
        result = await get_hint(state, 5)
        assert result["error"] is not None

    @pytest.mark.anyio
    async def test_api_failure_returns_error_not_exception(self):
        state = _make_state()
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.side_effect = RuntimeError("API down")
            result = await get_hint(state, 1)

        assert result["error"] is not None
        assert "Hint generation failed" in result["error"]
        assert result["content"] == ""

    @pytest.mark.anyio
    async def test_hint_content_stripped(self):
        state = _make_state()
        mock_resp = _mock_openai_response({
            "content": "  Start by validating...  ",
            "security_note": "  CWE-20 applies here.  ",
        })
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_resp
            result = await get_hint(state, 1)

        assert result["content"] == "Start by validating..."
        assert result["security_note"] == "CWE-20 applies here."


# =============================================================================
# get_security_hint tests
# =============================================================================

class TestGetSecurityHint:

    @pytest.mark.anyio
    async def test_short_code_returns_no_issue_without_api_call(self):
        state = _make_state()
        with patch("multiagent.agents.code_generator.client") as mock_client:
            result = await get_security_hint(state, "import sqlite3")
            mock_client.chat.completions.create.assert_not_called()

        assert result["has_issue"] is False
        assert result["error"] is None

    @pytest.mark.anyio
    async def test_empty_code_returns_no_issue(self):
        state = _make_state()
        result = await get_security_hint(state, "   ")
        assert result["has_issue"] is False

    @pytest.mark.anyio
    async def test_bad_code_returns_issue(self):
        state = _make_state()
        bad_code = (
            'import sqlite3\n\ndef verify(username, password):\n'
            '    conn = sqlite3.connect("db")\n'
            '    cursor = conn.cursor()\n'
            '    cursor.execute(f"SELECT * FROM users WHERE u = \'{username}\'")\n'
            '    row = cursor.fetchone()\n'
            '    return row is not None\n'
        )
        mock_resp = _mock_openai_response({
            "has_issue": True,
            "issue": "The query concatenates username using an f-string — SQL injection risk.",
            "suggestion": "Use a parameterised query with a ? placeholder instead.",
            "cwe_id": "CWE-89",
        })
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_resp
            result = await get_security_hint(state, bad_code)

        assert result["has_issue"] is True
        assert result["cwe_id"] == "CWE-89"
        assert result["issue"] != ""
        assert result["suggestion"] != ""
        assert result["error"] is None

    @pytest.mark.anyio
    async def test_api_failure_returns_no_issue_not_exception(self):
        state = _make_state()
        long_code = "import sqlite3\n" + "# some code\n" * 5
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.side_effect = RuntimeError("timeout")
            result = await get_security_hint(state, long_code)

        assert result["has_issue"] is False
        assert result["error"] is not None
        assert "Security hint failed" in result["error"]

    @pytest.mark.anyio
    async def test_null_cwe_becomes_none(self):
        state = _make_state()
        long_code = "import sqlite3\n" + "x = 1\n" * 5
        mock_resp = _mock_openai_response({
            "has_issue": True,
            "issue": "Missing input validation.",
            "suggestion": "Check types and lengths.",
            "cwe_id": None,
        })
        with patch("multiagent.agents.code_generator.client") as mock_client:
            mock_client.chat.completions.create.return_value = mock_resp
            result = await get_security_hint(state, long_code)

        assert result["cwe_id"] is None


# =============================================================================
# finalize_code tests
# =============================================================================

class TestFinalizeCode:

    def _make_annotations(self) -> CodingAnnotations:
        return {
            "what_does_code_do": "Validates inputs and queries the database securely.",
            "threats_addressed": ["SQL injection via parameterised query", "Input validation"],
            "submitted_at": datetime.now(timezone.utc).isoformat(),
        }

    def _make_hints(self) -> list[HintRecord]:
        return [
            {"level": 1, "timestamp": "2026-07-01T10:00:00Z"},
            {"level": 2, "timestamp": "2026-07-01T10:05:00Z"},
        ]

    def test_returns_user_code_as_generated_code(self):
        state = _make_state()
        user_code = "import sqlite3\n\ndef verify(u, p): ..."
        result = finalize_code(
            state,
            user_code=user_code,
            annotations=self._make_annotations(),
            confidence_rating=4,
            hints_requested=self._make_hints(),
            time_in_coding_seconds=300.0,
        )
        assert result["generated_code"] == user_code

    def test_current_stage_is_code_review(self):
        state = _make_state()
        result = finalize_code(
            state,
            user_code="def verify(): pass",
            annotations=self._make_annotations(),
            confidence_rating=3,
            hints_requested=[],
            time_in_coding_seconds=120.0,
        )
        assert result["current_stage"] == "code_review"

    def test_hint_level_reached_is_max_requested(self):
        state = _make_state()
        hints: list[HintRecord] = [
            {"level": 1, "timestamp": "2026-07-01T10:00:00Z"},
            {"level": 3, "timestamp": "2026-07-01T10:10:00Z"},
        ]
        result = finalize_code(
            state,
            user_code="...",
            annotations=self._make_annotations(),
            confidence_rating=2,
            hints_requested=hints,
            time_in_coding_seconds=600.0,
        )
        assert result["hitl_coding"]["hint_level_reached"] == 3

    def test_no_hints_gives_level_reached_zero(self):
        state = _make_state()
        result = finalize_code(
            state,
            user_code="import sqlite3",
            annotations=self._make_annotations(),
            confidence_rating=5,
            hints_requested=[],
            time_in_coding_seconds=180.0,
        )
        assert result["hitl_coding"]["hint_level_reached"] == 0

    def test_confidence_rating_clamped_to_1_5(self):
        state = _make_state()
        result_low = finalize_code(
            state, user_code="...", annotations=self._make_annotations(),
            confidence_rating=0, hints_requested=[], time_in_coding_seconds=60.0,
        )
        result_high = finalize_code(
            state, user_code="...", annotations=self._make_annotations(),
            confidence_rating=99, hints_requested=[], time_in_coding_seconds=60.0,
        )
        assert result_low["hitl_coding"]["confidence_rating"] == 1
        assert result_high["hitl_coding"]["confidence_rating"] == 5

    def test_time_is_rounded_to_one_decimal(self):
        state = _make_state()
        result = finalize_code(
            state, user_code="...", annotations=self._make_annotations(),
            confidence_rating=3, hints_requested=[], time_in_coding_seconds=123.456,
        )
        assert result["hitl_coding"]["time_in_coding_seconds"] == 123.5

    def test_annotations_stored_in_hitl_metrics(self):
        state = _make_state()
        annotations = self._make_annotations()
        result = finalize_code(
            state, user_code="...", annotations=annotations,
            confidence_rating=4, hints_requested=[], time_in_coding_seconds=200.0,
        )
        assert result["hitl_coding"]["annotations"] == annotations

    def test_hints_requested_preserved_in_order(self):
        state = _make_state()
        hints: list[HintRecord] = [
            {"level": 1, "timestamp": "2026-07-01T10:00:00Z"},
            {"level": 2, "timestamp": "2026-07-01T10:03:00Z"},
            {"level": 4, "timestamp": "2026-07-01T10:15:00Z"},
        ]
        result = finalize_code(
            state, user_code="...", annotations=self._make_annotations(),
            confidence_rating=2, hints_requested=hints, time_in_coding_seconds=900.0,
        )
        assert result["hitl_coding"]["hints_requested"] == hints

    def test_error_is_none_on_success(self):
        state = _make_state()
        result = finalize_code(
            state, user_code="...", annotations=self._make_annotations(),
            confidence_rating=3, hints_requested=[], time_in_coding_seconds=60.0,
        )
        assert result["error"] is None

    def test_code_explanation_is_none(self):
        state = _make_state()
        result = finalize_code(
            state, user_code="...", annotations=self._make_annotations(),
            confidence_rating=3, hints_requested=[], time_in_coding_seconds=60.0,
        )
        assert result["code_explanation"] is None


# =============================================================================
# run_code_generator (LangGraph node) tests
# =============================================================================

class TestRunCodeGeneratorNode:

    @pytest.mark.anyio
    async def test_sets_stage_to_coding_in_progress(self):
        state = _make_state()
        result = await run_code_generator(state)
        assert result["current_stage"] == "coding_in_progress"

    @pytest.mark.anyio
    async def test_does_not_generate_code(self):
        state = _make_state()
        result = await run_code_generator(state)
        assert result["generated_code"] is None

    @pytest.mark.anyio
    async def test_sets_hitl_metrics_to_none_initially(self):
        state = _make_state()
        result = await run_code_generator(state)
        assert result["hitl_coding"] is None

    @pytest.mark.anyio
    async def test_error_is_none(self):
        state = _make_state()
        result = await run_code_generator(state)
        assert result["error"] is None
