"""
tests/test_mcp_servers.py
--------------------------
Standalone tests for all three MCP servers.

Tests call the underlying Python functions directly — not via the MCP stdio
protocol — so they run without spinning up a full MCP server subprocess.

  bandit_server  — uses real Bandit (no mocking); needs bandit in PATH
  nist_nvd_server — httpx is mocked; no network calls
  sandbox_server  — uses real subprocess execution

Run:
    python -m pytest tests/test_mcp_servers.py -v
    python -m unittest tests.test_mcp_servers -v
"""

import asyncio
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_servers.bandit_server import _run_bandit
from mcp_servers.nist_nvd_server import _search_nvd
from mcp_servers.sandbox_server import _execute_code


# ===========================================================================
# Bandit server
# ===========================================================================

class TestBanditServer(unittest.TestCase):

    _CLEAN_CODE = """\
def add(a: int, b: int) -> int:
    return a + b
"""

    _SQL_INJECTION_CODE = """\
import sqlite3

def get_user(username):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE name = '" + username + "'")
    return cursor.fetchone()
"""

    _HARDCODED_PASSWORD_CODE = """\
import sqlite3

def connect_db():
    password = "super_secret_password"
    conn = sqlite3.connect(f"db_{password}.sqlite")
    return conn
"""

    def test_clean_code_returns_no_findings(self):
        result = _run_bandit(self._CLEAN_CODE)

        self.assertIsNone(result["error"])
        self.assertEqual(result["findings"], [])
        self.assertEqual(result["summary"]["total"], 0)

    def test_sql_injection_detected(self):
        result = _run_bandit(self._SQL_INJECTION_CODE)

        self.assertIsNone(result["error"])
        self.assertGreater(len(result["findings"]), 0)
        severities = [f["severity"] for f in result["findings"]]
        self.assertTrue(any(s in ("MEDIUM", "HIGH") for s in severities))

    def test_hardcoded_password_detected(self):
        result = _run_bandit(self._HARDCODED_PASSWORD_CODE)

        self.assertIsNone(result["error"])
        self.assertGreater(len(result["findings"]), 0)

    def test_result_has_required_keys(self):
        result = _run_bandit(self._CLEAN_CODE)

        self.assertIn("findings", result)
        self.assertIn("summary",  result)
        self.assertIn("error",    result)
        for key in ("total", "high", "medium", "low"):
            self.assertIn(key, result["summary"])

    def test_finding_has_required_keys(self):
        result = _run_bandit(self._SQL_INJECTION_CODE)

        if result["findings"]:
            finding = result["findings"][0]
            for key in ("test_id", "test_name", "severity", "confidence",
                        "description", "line_number", "cwe_id"):
                self.assertIn(key, finding)

    def test_summary_counts_match_findings(self):
        result = _run_bandit(self._SQL_INJECTION_CODE)

        total_from_counts = (
            result["summary"]["high"]
            + result["summary"]["medium"]
            + result["summary"]["low"]
        )
        self.assertEqual(result["summary"]["total"], len(result["findings"]))
        self.assertEqual(result["summary"]["total"], total_from_counts)

    def test_empty_string_does_not_crash(self):
        result = _run_bandit("")

        self.assertIn("findings", result)
        self.assertIsInstance(result["findings"], list)


# ===========================================================================
# NIST NVD server
# ===========================================================================

def _make_nvd_response(cve_id: str = "CVE-2024-0001") -> dict:
    return {
        "totalResults": 1,
        "vulnerabilities": [
            {
                "cve": {
                    "id": cve_id,
                    "descriptions": [
                        {"lang": "en", "value": "A test SQL injection vulnerability."}
                    ],
                    "published": "2024-01-15T00:00:00.000",
                    "metrics":   {},
                    "weaknesses": [
                        {"description": [{"value": "CWE-89"}]}
                    ],
                }
            }
        ],
    }


def _patch_httpx(mock_response: MagicMock):
    """
    Returns a context manager that patches httpx.AsyncClient so that
    async with httpx.AsyncClient(...) as client: client.get(...) returns
    mock_response.
    """
    mock_inner = AsyncMock()
    mock_inner.get = AsyncMock(return_value=mock_response)
    mock_async_cm = AsyncMock()
    mock_async_cm.__aenter__ = AsyncMock(return_value=mock_inner)
    mock_async_cm.__aexit__ = AsyncMock(return_value=None)
    return patch(
        "mcp_servers.nist_nvd_server.httpx.AsyncClient",
        return_value=mock_async_cm,
    ), mock_inner


class TestNVDServer(unittest.IsolatedAsyncioTestCase):

    def _mock_response(self, status_code: int, json_data: dict | None = None) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        if json_data is not None:
            resp.json.return_value = json_data
        resp.raise_for_status = MagicMock()
        return resp

    async def test_rate_limit_403_returns_error(self):
        mock_resp = self._mock_response(403)
        patcher, _ = _patch_httpx(mock_resp)
        with patcher:
            result = await _search_nvd("sql injection")

        self.assertEqual(result["cves"], [])
        self.assertIn("rate limit", result["error"].lower())

    async def test_rate_limit_429_returns_error(self):
        mock_resp = self._mock_response(429)
        patcher, _ = _patch_httpx(mock_resp)
        with patcher:
            result = await _search_nvd("sql injection")

        self.assertEqual(result["cves"], [])
        self.assertIn("429", result["error"])

    async def test_timeout_returns_error(self):
        import httpx

        mock_inner = AsyncMock()
        mock_inner.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
        mock_async_cm = AsyncMock()
        mock_async_cm.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("mcp_servers.nist_nvd_server.httpx.AsyncClient", return_value=mock_async_cm):
            result = await _search_nvd("sql injection")

        self.assertEqual(result["cves"], [])
        self.assertIn("timed out", result["error"].lower())

    async def test_successful_response_returns_cves(self):
        mock_resp = self._mock_response(200, _make_nvd_response())
        patcher, _ = _patch_httpx(mock_resp)
        with patcher:
            result = await _search_nvd("sql injection")

        self.assertIsNone(result["error"])
        self.assertEqual(len(result["cves"]), 1)
        self.assertEqual(result["cves"][0]["cve_id"], "CVE-2024-0001")
        self.assertEqual(result["keyword"],     "sql injection")
        self.assertEqual(result["total_found"], 1)

    async def test_cve_has_required_keys(self):
        mock_resp = self._mock_response(200, _make_nvd_response())
        patcher, _ = _patch_httpx(mock_resp)
        with patcher:
            result = await _search_nvd("injection")

        if result["cves"]:
            cve = result["cves"][0]
            for key in ("cve_id", "description", "published", "severity",
                        "cvss_score", "cwe_ids", "nvd_url"):
                self.assertIn(key, cve)

    async def test_cwe_ids_extracted(self):
        mock_resp = self._mock_response(200, _make_nvd_response())
        patcher, _ = _patch_httpx(mock_resp)
        with patcher:
            result = await _search_nvd("injection")

        if result["cves"]:
            self.assertIn("CWE-89", result["cves"][0]["cwe_ids"])

    async def test_max_results_capped_at_10(self):
        mock_resp = self._mock_response(200, {"totalResults": 0, "vulnerabilities": []})
        patcher, mock_inner = _patch_httpx(mock_resp)
        with patcher:
            await _search_nvd("test", max_results=999)

        params = mock_inner.get.call_args.kwargs.get("params", {})
        self.assertLessEqual(params.get("resultsPerPage", 0), 10)

    async def test_unexpected_error_returns_error_dict(self):
        mock_inner = AsyncMock()
        mock_inner.get = AsyncMock(side_effect=RuntimeError("unexpected!"))
        mock_async_cm = AsyncMock()
        mock_async_cm.__aenter__ = AsyncMock(return_value=mock_inner)
        mock_async_cm.__aexit__ = AsyncMock(return_value=None)

        with patch("mcp_servers.nist_nvd_server.httpx.AsyncClient", return_value=mock_async_cm):
            result = await _search_nvd("sql injection")

        self.assertEqual(result["cves"], [])
        self.assertIsNotNone(result["error"])
        self.assertIn("keyword", result)


# ===========================================================================
# Sandbox server
# ===========================================================================

class TestSandboxServer(unittest.IsolatedAsyncioTestCase):

    async def test_syntax_error_caught_before_subprocess(self):
        result = await _execute_code("def broken(:\n    pass")

        self.assertFalse(result["passed"])
        self.assertIn("SyntaxError", result["stderr"])
        self.assertEqual(result["exit_code"], 1)
        self.assertFalse(result["timed_out"])
        self.assertIsNone(result["error"])

    async def test_clean_code_passes(self):
        result = await _execute_code("x = 1 + 1\n")

        self.assertTrue(result["passed"])
        self.assertEqual(result["exit_code"], 0)
        self.assertFalse(result["timed_out"])
        self.assertIsNone(result["error"])

    async def test_stdout_captured(self):
        result = await _execute_code('print("hello world")\n')

        self.assertTrue(result["passed"])
        self.assertIn("hello world", result["stdout"])

    async def test_runtime_exception_fails(self):
        result = await _execute_code("raise ValueError('oops')\n")

        self.assertFalse(result["passed"])
        self.assertNotEqual(result["exit_code"], 0)
        self.assertIn("ValueError", result["stderr"])

    async def test_nonzero_exit_code_fails(self):
        result = await _execute_code("import sys\nsys.exit(2)\n")

        self.assertFalse(result["passed"])
        self.assertEqual(result["exit_code"], 2)

    async def test_result_has_required_keys(self):
        result = await _execute_code("pass\n")

        for key in ("passed", "stdout", "stderr", "exit_code", "timed_out", "error"):
            self.assertIn(key, result)

    async def test_timeout_kills_process(self):
        with patch("mcp_servers.sandbox_server.TIMEOUT_SECONDS", 1):
            result = await _execute_code("while True:\n    pass\n")

        self.assertFalse(result["passed"])
        self.assertTrue(result["timed_out"])

    async def test_output_truncated_at_max_bytes(self):
        big_output = "print('A' * 5000)\n"

        with patch("mcp_servers.sandbox_server.MAX_OUTPUT_BYTES", 100):
            result = await _execute_code(big_output)

        self.assertIn("[output truncated]", result["stdout"])
        self.assertLessEqual(len(result["stdout"].encode()), 150)


# ===========================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)
