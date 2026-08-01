"""
mcp_servers/bandit_server.py
-----------------------------
MCP server that runs Bandit static security analysis on Python code.

Exposes one tool: run_bandit(code) -> findings JSON.

Used by: Code Reviewer and Verifier agents independently.
Each agent makes its own call: results are never shared between them.

Run standalone to test before wiring into MultiServerMCPClient:
    python mcp_servers/bandit_server.py --test
"""

import asyncio
import json
import os
import subprocess
import sys
import tempfile

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Server instance ────────────────────────────────────────────────────────────

# The Server object is the MCP server. The string "bandit-server" is its name,
# which is how it identifies itself to clients during the handshake.
app = Server("bandit-server")

TOOL_NAME = "run_bandit"

# ── Core Bandit logic ──────────────────────────────────────────────────────────

def _run_bandit(code: str) -> dict:
    """
    Writes code to a temp file, runs Bandit on it, parses the output,
    cleans up the temp file, and returns a structured findings dict.

    This is a plain function (not async) so it can be called both from
    the MCP tool handler and from the standalone --test mode.

    Bandit exit codes:
      0 = analysis ran, no issues found
      1 = analysis ran, issues found  (this is normal: not an error)
      2 = Bandit itself crashed or could not run

    Returns
    -------
    dict with keys:
      findings : list of issue dicts
      summary  : counts by severity
      error    : error message string or None
    """
    tmp_path = None
    try:
        # Write the code to a temporary .py file on disk.
        # Bandit requires a real file: it cannot read from stdin.
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".py",
            delete=False,
            encoding="utf-8",
        ) as f:
            f.write(code)
            tmp_path = f.name

        # Run Bandit as a subprocess.
        # -f json  : output in JSON format
        # -q       : quiet mode: suppress progress output
        # timeout  : kill the process if it takes more than 30 seconds
        result = subprocess.run(
            ["bandit", "-f", "json", "-q", tmp_path],
            stdin=subprocess.DEVNULL,   # prevent inheriting the MCP stdio pipe
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Exit code 2 means Bandit itself failed (bad arguments, crash, etc.)
        # Exit codes 0 and 1 both mean Bandit ran successfully.
        if result.returncode == 2:
            return {
                "findings": [],
                "summary": {"total": 0, "high": 0, "medium": 0, "low": 0},
                "error": f"Bandit failed to run: {result.stderr.strip()}",
            }

        # Parse Bandit's JSON output.
        raw = json.loads(result.stdout)

        # Normalise each finding into a consistent structure.
        # Bandit's raw output has verbose field names: we simplify them.
        findings = []
        for r in raw.get("results", []):
            # Bandit provides CWE data as a nested object with an 'id' field.
            cwe_data = r.get("issue_cwe", {})
            cwe_id = f"CWE-{cwe_data['id']}" if cwe_data.get("id") else None

            findings.append({
                "test_id":      r.get("test_id"),
                # e.g. "B106" - Bandit's own test identifier
                "test_name":    r.get("test_name"),
                # e.g. "hardcoded_password_funcarg"
                "severity":     r.get("issue_severity"),
                # "HIGH", "MEDIUM", or "LOW"
                "confidence":   r.get("issue_confidence"),
                # How confident Bandit is in the finding
                "description":  r.get("issue_text"),
                # Human-readable description of the issue
                "line_number":  r.get("line_number"),
                # Line in the code where the issue was found
                "cwe_id":       cwe_id,
                # e.g. "CWE-89" - maps to our CWE corpus
                "code_snippet": r.get("code", "").strip(),
                # The actual line(s) of code that triggered the finding
            })

        # Extract severity counts from Bandit's metrics section.
        totals = raw.get("metrics", {}).get("_totals", {})
        summary = {
            "total":  len(findings),
            "high":   int(totals.get("SEVERITY.HIGH",   0)),
            "medium": int(totals.get("SEVERITY.MEDIUM", 0)),
            "low":    int(totals.get("SEVERITY.LOW",    0)),
        }

        return {"findings": findings, "summary": summary, "error": None}

    except json.JSONDecodeError:
        # Bandit produced output that is not valid JSON.
        return {
            "findings": [],
            "summary": {"total": 0, "high": 0, "medium": 0, "low": 0},
            "error": "Failed to parse Bandit output as JSON.",
        }

    except subprocess.TimeoutExpired:
        return {
            "findings": [],
            "summary": {"total": 0, "high": 0, "medium": 0, "low": 0},
            "error": "Bandit timed out after 30 seconds.",
        }

    finally:
        # Always delete the temp file, even if something went wrong above.
        # The finally block runs whether or not an exception was raised.
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ── MCP tool definitions ───────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    Tells MCP clients which tools this server exposes.

    Called automatically by the client during initialisation.
    The inputSchema is a JSON Schema object describing what arguments
    the tool accepts: the client validates calls against this.
    """
    return [
        Tool(
            name=TOOL_NAME,
            description=(
                "Runs Bandit static security analysis on Python source code. "
                "Returns a list of security findings with severity, CWE mapping, "
                "line numbers, and code snippets, plus a summary of finding counts "
                "by severity level."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python source code to analyse for security issues.",
                    }
                },
                "required": ["code"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Handles a tool call from an agent.

    The MCP framework calls this function whenever an agent calls a tool
    on this server. We check the tool name, run the analysis, and return
    the result as a TextContent object containing a JSON string.

    TextContent is an MCP type: it wraps text to be returned to the agent.
    The agent receives it as a string and parses the JSON itself.
    """
    if name != TOOL_NAME:
        raise ValueError(f"Unknown tool '{name}'. This server only exposes '{TOOL_NAME}'.")

    code = arguments.get("code", "")

    if not code.strip():
        result = {
            "findings": [],
            "summary": {"total": 0, "high": 0, "medium": 0, "low": 0},
            "error": "No code was provided.",
        }
    else:
        result = _run_bandit(code)

    # json.dumps converts the dict to a JSON string.
    # TextContent wraps it in the format MCP expects.
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ── MCP server entry point ─────────────────────────────────────────────────────

async def _serve() -> None:
    """
    Starts the MCP server and keeps it running until the client disconnects.

    stdio_server() sets up the stdin/stdout communication channels.
    app.run() starts the main loop that listens for tool calls and responds.
    This runs as a subprocess managed by MultiServerMCPClient.
    """
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


# ── Standalone test mode ───────────────────────────────────────────────────────

def _run_test() -> None:
    """
    Tests the Bandit integration directly without the MCP protocol.

    Run with: python mcp_servers/bandit_server.py --test

    Uses a code sample with three known vulnerabilities so you can verify
    Bandit is installed and producing the expected output before wiring
    the server into MultiServerMCPClient.
    """
    test_code = '''
import subprocess
import hashlib

def login(username, password, db):
    # CWE-89: SQL injection via string concatenation
    query = "SELECT * FROM users WHERE username = '" + username + "'"
    db.execute(query)

    # CWE-916: weak hashing algorithm for passwords
    hashed = hashlib.md5(password.encode()).hexdigest()

    # CWE-78: shell injection via subprocess with shell=True
    subprocess.run("echo " + username, shell=True)
'''

    print("Running Bandit on test code with known vulnerabilities...\n")
    result = _run_bandit(test_code)

    print(f"Summary: {result['summary']}")
    print(f"Error:   {result['error']}\n")

    if result["findings"]:
        print("Findings:")
        for f in result["findings"]:
            print(
                f"  Line {f['line_number']:>3} | {f['severity']:<6} | "
                f"{f['test_id']} | {f['cwe_id'] or 'N/A'} | {f['description']}"
            )
    else:
        print("No findings returned.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        _run_test()
    else:
        asyncio.run(_serve())
