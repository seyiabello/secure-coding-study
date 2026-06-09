"""
tests/test_baseline.py
----------------------
Unit tests for baseline/agent.py.

Uses unittest.mock throughout — no real API calls are made.
"""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch


class TestRunBaseline(unittest.TestCase):

    def _make_client(self, content: str) -> MagicMock:
        client = MagicMock()
        message = MagicMock()
        message.content = content
        choice = MagicMock()
        choice.message = message
        client.chat.completions.create.return_value = MagicMock(choices=[choice])
        return client

    def test_returns_model_content(self):
        from baseline.agent import run_baseline
        client = self._make_client("def hello(): pass")
        result = run_baseline("Write hello world", client=client)
        self.assertEqual(result, "def hello(): pass")

    def test_calls_correct_model_and_temperature(self):
        from baseline.agent import run_baseline
        from config import MODEL, TEMPERATURE
        client = self._make_client("")
        run_baseline("task", client=client)
        call_kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], MODEL)
        self.assertEqual(call_kwargs["temperature"], TEMPERATURE)

    def test_sends_system_and_user_messages(self):
        from baseline.agent import run_baseline
        from baseline.prompts import SYSTEM_PROMPT
        client = self._make_client("")
        run_baseline("Write a parser", client=client)
        messages = client.chat.completions.create.call_args.kwargs["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], SYSTEM_PROMPT)
        self.assertEqual(messages[1]["role"], "user")
        self.assertEqual(messages[1]["content"], "Write a parser")

    def test_no_security_instructions_in_system_prompt(self):
        from baseline.prompts import SYSTEM_PROMPT
        lowered = SYSTEM_PROMPT.lower()
        for term in ("security", "vulnerability", "threat", "injection", "cwe"):
            self.assertNotIn(term, lowered, f"Security term '{term}' found in baseline prompt")


class TestLogSession(unittest.TestCase):

    def test_writes_jsonl_record_with_correct_schema(self):
        from baseline.agent import log_session
        from config import MODEL, TEMPERATURE

        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("baseline.agent.LOG_FILE", tmp_path):
                log_session("P01", "Write a login form", "def login(): ...", 3.5)

            with open(tmp_path, encoding="utf-8") as f:
                record = json.loads(f.readline())

            self.assertEqual(record["condition"], "baseline")
            self.assertEqual(record["participant_id"], "P01")
            self.assertEqual(record["model"], MODEL)
            self.assertEqual(record["temperature"], TEMPERATURE)
            self.assertEqual(record["task"], "Write a login form")
            self.assertEqual(record["response"], "def login(): ...")
            self.assertEqual(record["duration_seconds"], 3.5)
            self.assertIn("timestamp", record)
        finally:
            os.unlink(tmp_path)

    def test_appends_multiple_records(self):
        from baseline.agent import log_session

        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("baseline.agent.LOG_FILE", tmp_path):
                log_session("P01", "task one", "response one", 1.0)
                log_session("P02", "task two", "response two", 2.0)

            with open(tmp_path, encoding="utf-8") as f:
                lines = f.readlines()

            self.assertEqual(len(lines), 2)
            self.assertEqual(json.loads(lines[0])["participant_id"], "P01")
            self.assertEqual(json.loads(lines[1])["participant_id"], "P02")
        finally:
            os.unlink(tmp_path)

    def test_timestamp_is_utc_iso8601(self):
        from baseline.agent import log_session
        import datetime

        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("baseline.agent.LOG_FILE", tmp_path):
                log_session("P01", "task", "response", 1.0)

            with open(tmp_path, encoding="utf-8") as f:
                record = json.loads(f.readline())

            # Must be parseable as an ISO 8601 datetime
            ts = datetime.datetime.fromisoformat(record["timestamp"])
            self.assertIsNotNone(ts)
        finally:
            os.unlink(tmp_path)

    def test_duration_rounded_to_three_decimal_places(self):
        from baseline.agent import log_session

        with tempfile.NamedTemporaryFile(mode="r", suffix=".jsonl", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            with patch("baseline.agent.LOG_FILE", tmp_path):
                log_session("P01", "task", "response", 1.23456789)

            with open(tmp_path, encoding="utf-8") as f:
                record = json.loads(f.readline())

            self.assertEqual(record["duration_seconds"], 1.235)
        finally:
            os.unlink(tmp_path)


if __name__ == "__main__":
    unittest.main()
