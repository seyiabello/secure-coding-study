"""
mcp_servers/sandbox_server.py
------------------------------
MCP server that executes Python code in a restricted subprocess and
returns the execution result.

Exposes one tool: execute_code(code) -> execution result JSON.

Used by: Verifier only.
The Verifier runs the final generated code here to check it executes
without errors, independently of the static analysis done by Bandit.

Restrictions applied:
  - 10 second execution timeout (process is forcibly killed on expiry)
  - Code runs in an isolated temp directory, not the project folder
  - stdin explicitly closed (subprocess.DEVNULL) — code cannot read input
  - stdout and stderr capped at 4 KB each
  - Syntax checked with ast.parse before subprocess is spawned

Implementation note:
  Uses asyncio.create_subprocess_exec (not subprocess.Popen) because the
  sandbox server itself runs as a subprocess of MultiServerMCPClient with
  redirected stdio. Using asyncio.create_subprocess_exec with
  stdin=DEVNULL ensures the inner subprocess has clean, closed stdin and
  does not inherit the parent's MCP communication pipes.

Run standalone to test before wiring into MultiServerMCPClient:
    python mcp_servers/sandbox_server.py --test
"""

import ast
import asyncio
import json
import os
import sys
import tempfile

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

# ── Server instance ────────────────────────────────────────────────────────────

app = Server("sandbox-server")

TOOL_NAME = "execute_code"

# ── Execution constants ────────────────────────────────────────────────────────

TIMEOUT_SECONDS  = 10     # kill the subprocess after this many seconds
MAX_OUTPUT_BYTES = 4096   # cap stdout and stderr at 4 KB each

# ── Core execution logic ───────────────────────────────────────────────────────

async def _execute_code(code: str) -> dict:
    """
    Executes Python code in a restricted subprocess and returns the result.

    Steps:
      1. Check syntax with ast.parse — catches errors before spawning anything
      2. Write the code to a temp file in an isolated temp directory
      3. Run the file as an async subprocess with stdin closed
      4. Wait for completion with asyncio.wait_for (kills on timeout)
      5. Capture and truncate stdout and stderr
      6. Clean up the temp file

    Uses asyncio.create_subprocess_exec so this integrates cleanly with the
    MCP server's event loop. No thread pool needed.

    Returns
    -------
    dict with keys:
      passed     : True if exit_code == 0 and no timeout
      stdout     : captured standard output (truncated if > MAX_OUTPUT_BYTES)
      stderr     : captured standard error (truncated if > MAX_OUTPUT_BYTES)
      exit_code  : the process exit code (0 = success, non-zero = failure)
      timed_out  : True if the process was killed for exceeding the timeout
      error      : error message if something went wrong at the sandbox level
    """
    # ── Step 1: Syntax check ───────────────────────────────────────────────────
    # ast.parse compiles the code without executing it.
    # If the code has a syntax error, we catch it here cleanly without
    # needing to spawn a subprocess at all.
    try:
        ast.parse(code)
    except SyntaxError as e:
        return {
            "passed":    False,
            "stdout":    "",
            "stderr":    f"SyntaxError on line {e.lineno}: {e.msg}",
            "exit_code": 1,
            "timed_out": False,
            "error":     None,
        }

    tmp_dir  = None
    tmp_path = None

    try:
        # ── Step 2: Write code to isolated temp directory ──────────────────────
        # Using a dedicated temp directory keeps the code's working directory
        # separate from the project folder so it cannot reach project files
        # via relative paths.
        tmp_dir = tempfile.mkdtemp()
        tmp_path = os.path.join(tmp_dir, "code_under_test.py")

        with open(tmp_path, "w", encoding="utf-8") as f:
            f.write(code)

        # ── Step 3: Spawn async subprocess ────────────────────────────────────
        # asyncio.create_subprocess_exec launches the subprocess and integrates
        # it with the running event loop.
        #
        # stdin=DEVNULL: explicitly closes stdin so the subprocess cannot
        #   read from the parent's MCP communication pipe. This is critical
        #   when the sandbox server is itself running as a subprocess with
        #   redirected stdio (which MultiServerMCPClient does).
        #
        # sys.executable: path to the current Python interpreter, so the
        #   code runs in the same virtual environment as the project.
        #
        # cwd=tmp_dir: the subprocess's working directory is the isolated
        #   temp folder, not the project directory.
        proc = await asyncio.create_subprocess_exec(
            sys.executable, tmp_path,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmp_dir,
        )

        # ── Step 4: Wait with timeout ──────────────────────────────────────────
        # asyncio.wait_for cancels the communicate() coroutine if the timeout
        # expires. We then kill the process and collect any partial output.
        timed_out = False
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            proc.kill()
            stdout_bytes, stderr_bytes = await proc.communicate()
            timed_out = True

        # Decode bytes to strings. errors="replace" prevents crashes from
        # code that prints non-UTF-8 bytes.
        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")
        exit_code = proc.returncode

        # ── Step 5: Truncate output ────────────────────────────────────────────
        # Cap stdout and stderr so a runaway print loop cannot fill memory.
        if len(stdout) > MAX_OUTPUT_BYTES:
            stdout = stdout[:MAX_OUTPUT_BYTES] + "\n[output truncated]"
        if len(stderr) > MAX_OUTPUT_BYTES:
            stderr = stderr[:MAX_OUTPUT_BYTES] + "\n[output truncated]"

        # passed = True only if the process exited normally with code 0.
        passed = (exit_code == 0) and (not timed_out)

        return {
            "passed":    passed,
            "stdout":    stdout,
            "stderr":    stderr,
            "exit_code": exit_code,
            "timed_out": timed_out,
            "error":     None,
        }

    except Exception as e:
        # This catches errors in the sandbox infrastructure itself, not
        # errors in the code being tested. Should rarely occur.
        return {
            "passed":    False,
            "stdout":    "",
            "stderr":    "",
            "exit_code": -1,
            "timed_out": False,
            "error":     f"Sandbox error: {str(e)}",
        }

    finally:
        # ── Step 6: Clean up temp files ────────────────────────────────────────
        # Always runs, even if an exception was raised above.
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        if tmp_dir and os.path.exists(tmp_dir):
            try:
                os.rmdir(tmp_dir)
            except OSError:
                # rmdir fails if the code created files in the temp dir.
                # The OS will clean up temp dirs eventually.
                pass


# ── MCP tool definitions ───────────────────────────────────────────────────────

@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    Tells MCP clients which tools this server exposes.
    Called automatically when the client connects.
    """
    return [
        Tool(
            name=TOOL_NAME,
            description=(
                "Executes Python source code in a restricted subprocess with a "
                f"{TIMEOUT_SECONDS}-second timeout. Returns whether execution "
                "succeeded, stdout, stderr, exit code, and whether the process "
                "timed out. Checks syntax before running. Use this to verify "
                "generated code executes without errors."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python source code to execute.",
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

    Calls _execute_code (async) directly — no thread pool needed because
    the subprocess is managed by the event loop via asyncio.create_subprocess_exec.
    """
    if name != TOOL_NAME:
        raise ValueError(
            f"Unknown tool '{name}'. This server only exposes '{TOOL_NAME}'."
        )

    code = arguments.get("code", "")

    if not code.strip():
        result = {
            "passed":    False,
            "stdout":    "",
            "stderr":    "",
            "exit_code": -1,
            "timed_out": False,
            "error":     "No code was provided.",
        }
    else:
        result = await _execute_code(code)

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


# ── MCP server entry point ─────────────────────────────────────────────────────

async def _serve() -> None:
    """
    Starts the MCP server on stdio and keeps it running.
    Managed as a subprocess by MultiServerMCPClient.
    """
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options(),
        )


# ── Standalone test mode ───────────────────────────────────────────────────────

async def _run_test() -> None:
    """
    Tests the sandbox directly without the MCP protocol.

    Run with: python mcp_servers/sandbox_server.py --test

    Runs four test cases to verify all execution paths work correctly:
      1. Code that runs successfully
      2. Code with a syntax error
      3. Code that raises a runtime exception
      4. Code that exceeds the timeout
    """
    test_cases = [
        {
            "label": "1. Working code",
            "code": (
                "def add(a, b):\n"
                "    return a + b\n\n"
                "result = add(3, 4)\n"
                "print(f'Result: {result}')\n"
            ),
        },
        {
            "label": "2. Syntax error",
            "code": "def broken(\n    print('missing closing paren'\n",
        },
        {
            "label": "3. Runtime exception",
            "code": (
                "data = {'key': 'value'}\n"
                "print(data['missing_key'])\n"
            ),
        },
        {
            "label": "4. Timeout (infinite loop)",
            "code": "while True:\n    pass\n",
        },
    ]

    for case in test_cases:
        print(f"--- {case['label']} ---")
        result = await _execute_code(case["code"])
        print(f"  passed:    {result['passed']}")
        print(f"  exit_code: {result['exit_code']}")
        print(f"  timed_out: {result['timed_out']}")
        if result["stdout"]:
            print(f"  stdout:    {result['stdout'].strip()}")
        if result["stderr"]:
            print(f"  stderr:    {result['stderr'].strip()[:100]}")
        if result["error"]:
            print(f"  error:     {result['error']}")
        print()


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        asyncio.run(_serve())
