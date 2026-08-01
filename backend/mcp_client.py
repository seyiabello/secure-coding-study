"""
mcp_client.py
-------------
Unified MCP client that connects to all three MCP servers.

This is the only file agents import for tool access. It encapsulates
the server configuration and provides a single call_tool() function
so agents never need to know which server provides which tool.

Servers managed:
  bandit   -> mcp_servers/bandit_server.py   -> tool: run_bandit
  nist_nvd -> mcp_servers/nist_nvd_server.py -> tool: search_nvd
  sandbox  -> mcp_servers/sandbox_server.py  -> tool: execute_code

Usage in agent code (langchain-mcp-adapters >= 0.1.0 API):
    from mcp_client import get_client, call_tool

    client = get_client()
    result = await call_tool(client, "run_bandit", {"code": code})

Run standalone to verify all three servers connect and respond:
    python mcp_client.py --test
"""

import asyncio
import json
import sys
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

# ── Server configuration ───────────────────────────────────────────────────────

# Use absolute paths to the server scripts so the client works correctly
# regardless of which directory the calling code is run from.
_SERVERS_DIR = Path(__file__).parent / "mcp_servers"

SERVER_CONFIG = {
    # Each key is a logical server name (arbitrary, used only for grouping).
    # 'command' is the executable to start the server.
    # 'args' is the script to run.
    # 'transport' tells MultiServerMCPClient to communicate over stdin/stdout.
    "bandit": {
        "command": sys.executable,
        "args":    [str(_SERVERS_DIR / "bandit_server.py")],
        "transport": "stdio",
    },
    "nist_nvd": {
        "command": sys.executable,
        "args":    [str(_SERVERS_DIR / "nist_nvd_server.py")],
        "transport": "stdio",
    },
    "sandbox": {
        "command": sys.executable,
        "args":    [str(_SERVERS_DIR / "sandbox_server.py")],
        "transport": "stdio",
    },
}

# ── Client factory ─────────────────────────────────────────────────────────────

def get_client() -> MultiServerMCPClient:
    """
    Returns a configured MultiServerMCPClient.

    As of langchain-mcp-adapters 0.1.0, MultiServerMCPClient is no longer
    an async context manager. Create it once per agent invocation and pass
    it to call_tool():

        client = get_client()
        result = await call_tool(client, "run_bandit", {"code": code})

    The client starts its server subprocesses lazily when get_tools() is
    first awaited. Each call to call_tool() awaits get_tools() internally,
    so no explicit setup step is needed in agent code.
    """
    return MultiServerMCPClient(SERVER_CONFIG)


# ── Tool call helper ───────────────────────────────────────────────────────────

async def call_tool(
    client: MultiServerMCPClient,
    tool_name: str,
    arguments: dict,
) -> dict:
    """
    Calls a tool by name and returns the parsed result dict.

    The client has a flat list of all tools from all servers combined.
    We find the tool by name, call it with the provided arguments, and
    parse the JSON string it returns back into a Python dict.

    Parameters
    ----------
    client    : active MultiServerMCPClient context (from get_client())
    tool_name : exact name of the tool: one of "run_bandit", "search_nvd",
                "execute_code"
    arguments : dict of arguments matching the tool's input schema

    Returns
    -------
    Parsed dict from the tool. Shape depends on the tool:
      run_bandit    -> {"findings": [...], "summary": {...}, "error": ...}
      search_nvd    -> {"cves": [...], "total_found": ..., "error": ...}
      execute_code  -> {"passed": ..., "stdout": ..., "stderr": ..., ...}

    Raises
    ------
    ValueError  if tool_name is not found in the connected servers
    json.JSONDecodeError  if the tool returns malformed JSON (should not happen)
    """
    # client.get_tools() is async in langchain-mcp-adapters >= 0.1.0.
    # It connects to the servers (if not already connected) and returns
    # a flat list of LangChain BaseTool objects, one per MCP tool across
    # all connected servers.
    tool_map = {t.name: t for t in await client.get_tools()}

    if tool_name not in tool_map:
        available = sorted(tool_map.keys())
        raise ValueError(
            f"Unknown tool '{tool_name}'. "
            f"Available tools: {available}"
        )

    # ainvoke() sends the call to the server over stdio MCP and waits
    # for the response. It returns the tool's text output as a string.
    raw = await tool_map[tool_name].ainvoke(arguments)

    # All three of our servers return JSON strings via TextContent.
    # Parse them back to dicts so calling code works with Python objects.
    if isinstance(raw, str):
        return json.loads(raw)

    # langchain-mcp-adapters 0.1.0 returns a list of content-part dicts,
    # e.g. [{"type": "text", "text": "..json..", "id": "..."}]
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict):
            text = first.get("text", "")
        elif hasattr(first, "text"):
            text = first.text
        else:
            text = str(first)
        return json.loads(text)

    # Already a dict (defensive: should not normally happen).
    if isinstance(raw, dict):
        return raw

    raise ValueError(
        f"Unexpected return type from tool '{tool_name}': {type(raw)}"
    )


# ── Standalone test mode ───────────────────────────────────────────────────────

async def _run_test() -> None:
    """
    Tests all three MCP servers via the unified client.

    Run with: python mcp_client.py --test

    Verifies:
      1. All three servers start and connect successfully
      2. run_bandit: detects a weak hashing issue in test code
      3. search_nvd: returns real CVEs for "authentication bypass"
      4. execute_code: runs simple working code and captures output
    """
    print("Connecting to all MCP servers...\n")
    client = get_client()

    # Confirm which tools are available across all servers.
    # This is the first await, which triggers the actual server connections.
    tools = await client.get_tools()
    tool_names = sorted(t.name for t in tools)
    print(f"Connected. {len(tools)} tools available: {tool_names}\n")

    # ── Test 1: run_bandit ─────────────────────────────────────────────────────
    print("--- Test 1: run_bandit ---")
    code_with_issue = (
        "import hashlib\n"
        "password = 'secret'\n"
        "hashed = hashlib.md5(password.encode()).hexdigest()\n"
        "print(hashed)\n"
    )
    bandit_result = await call_tool(client, "run_bandit", {"code": code_with_issue})
    print(f"  error:    {bandit_result['error']}")
    print(f"  summary:  {bandit_result['summary']}")
    if bandit_result["findings"]:
        f = bandit_result["findings"][0]
        print(f"  finding:  {f['test_id']} | {f['severity']} | {f['cwe_id']} | {f['description']}")
    print()

    # ── Test 2: search_nvd ─────────────────────────────────────────────────────
    print("--- Test 2: search_nvd ---")
    nvd_result = await call_tool(
        client, "search_nvd", {"keyword": "authentication bypass", "max_results": 2}
    )
    print(f"  error:       {nvd_result['error']}")
    print(f"  total_found: {nvd_result['total_found']}")
    for cve in nvd_result["cves"]:
        print(f"  {cve['cve_id']} | {cve['severity']} | CWEs: {cve['cwe_ids']}")
    print()

    # ── Test 3: execute_code ───────────────────────────────────────────────────
    print("--- Test 3: execute_code ---")
    working_code = (
        "def greet(name):\n"
        "    return f'Hello, {name}'\n\n"
        "print(greet('researcher'))\n"
    )
    sandbox_result = await call_tool(client, "execute_code", {"code": working_code})
    print(f"  error:     {sandbox_result['error']}")
    print(f"  passed:    {sandbox_result['passed']}")
    print(f"  exit_code: {sandbox_result['exit_code']}")
    print(f"  stdout:    {sandbox_result['stdout'].strip()}")
    print()

    print("All tests complete.")


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        print(
            "mcp_client.py is a library module. Import it from agent code.\n"
            "To run the connectivity test: python mcp_client.py --test"
        )
