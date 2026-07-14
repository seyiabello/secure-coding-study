"""
mcp_servers/nist_nvd_server.py
-------------------------------
MCP server that queries the NIST National Vulnerability Database (NVD)
REST API v2 for recent CVEs matching a keyword.

Exposes one tool: search_nvd(keyword, max_results) -> CVE list JSON.

Used by: Threat Modeller only.
The Threat Modeller calls this before writing the threat model so it can
ground threats in real, recently published vulnerabilities rather than
relying solely on GPT-4o's training data.

API docs: https://nvd.nist.gov/developers/vulnerabilities

Rate limits (rolling 30-second window):
  Without NVD_API_KEY : 5 requests
  With    NVD_API_KEY : 50 requests

Add NVD_API_KEY to your .env file to increase the limit. Get a free key at:
https://nvd.nist.gov/developers/request-an-api-key

Run standalone to test before wiring into MultiServerMCPClient:
    python mcp_servers/nist_nvd_server.py --test
"""

import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

load_dotenv()

# ── Server instance ────────────────────────────────────────────────────────────

app = Server("nist-nvd-server")

TOOL_NAME = "search_nvd"

# ── NVD API constants ──────────────────────────────────────────────────────────

NVD_API_URL  = "https://services.nvd.nist.gov/rest/json/cves/2.0"
MAX_RESULTS  = 5     # default number of CVEs to return per search
MAX_CAP      = 10    # hard cap — never return more than this to keep prompts short
REQUEST_TIMEOUT = 10.0  # seconds before giving up on the API call

# ── Core NVD query logic ───────────────────────────────────────────────────────

async def _search_nvd(keyword: str, max_results: int = MAX_RESULTS) -> dict:
    """
    Queries the NVD REST API v2 for CVEs matching the keyword.

    The NVD API is public and free. We use httpx for async HTTP so this
    function does not block the MCP server's event loop while waiting for
    the network response.

    Returns
    -------
    dict with keys:
      cves        : list of normalised CVE dicts
      total_found : total number of matching CVEs in NVD (may be more than returned)
      keyword     : the search term used
      error       : error message string or None
    """
    # Cap max_results to keep agent prompts a reasonable length.
    max_results = min(max(1, max_results), MAX_CAP)

    params = {
        "keywordSearch":  keyword,
        "resultsPerPage": max_results,
    }

    # If an NVD API key is set, include it in the request header.
    # This raises the rate limit from 5 to 50 requests per 30 seconds.
    headers = {}
    api_key = os.environ.get("NVD_API_KEY")
    if api_key:
        headers["apiKey"] = api_key

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
            response = await client.get(NVD_API_URL, params=params, headers=headers)

            # Handle rate limiting. NVD returns 403 or 429 when the limit is hit.
            if response.status_code == 403:
                return {
                    "cves": [], "total_found": 0, "keyword": keyword,
                    "error": (
                        "NVD API rate limit reached. "
                        "Add NVD_API_KEY to .env for a higher limit, "
                        "or wait 30 seconds and try again."
                    ),
                }
            if response.status_code == 429:
                return {
                    "cves": [], "total_found": 0, "keyword": keyword,
                    "error": "NVD API rate limit (429). Wait 30 seconds and retry.",
                }

            response.raise_for_status()
            data = response.json()

    except httpx.TimeoutException:
        return {
            "cves": [], "total_found": 0, "keyword": keyword,
            "error": f"NVD API request timed out after {REQUEST_TIMEOUT}s.",
        }
    except httpx.HTTPStatusError as e:
        return {
            "cves": [], "total_found": 0, "keyword": keyword,
            "error": f"NVD API HTTP error: {e.response.status_code}",
        }
    except Exception as e:
        return {
            "cves": [], "total_found": 0, "keyword": keyword,
            "error": f"Unexpected error calling NVD API: {str(e)}",
        }

    # ── Normalise the response ─────────────────────────────────────────────────
    # NVD returns deeply nested JSON. We flatten it into a clean list
    # of dicts that agents can read without navigating the raw structure.

    total_found = data.get("totalResults", 0)
    vulnerabilities = data.get("vulnerabilities", [])
    cves = []

    for item in vulnerabilities:
        cve = item.get("cve", {})

        # Extract English description only.
        # NVD provides descriptions in multiple languages — we want English.
        descriptions = cve.get("descriptions", [])
        description = next(
            (d["value"] for d in descriptions if d.get("lang") == "en"),
            "No English description available.",
        )

        # Extract CVSS v3 score and severity.
        # NVD may have v3.1 or v3.0 metrics — check both.
        severity  = "N/A"
        cvss_score = None
        for metric_key in ("cvssMetricV31", "cvssMetricV30"):
            metrics = cve.get("metrics", {}).get(metric_key, [])
            if metrics:
                cvss_data = metrics[0].get("cvssData", {})
                severity   = cvss_data.get("baseSeverity", "N/A")
                cvss_score = cvss_data.get("baseScore")
                break

        # Extract CWE IDs associated with this CVE.
        # Each weakness entry can contain multiple CWE references.
        cwe_ids = []
        for weakness in cve.get("weaknesses", []):
            for desc in weakness.get("description", []):
                value = desc.get("value", "")
                # NVD sometimes stores "NVD-CWE-Other" or "NVD-CWE-noinfo"
                # instead of a real CWE ID. We only keep real CWE IDs.
                if value.startswith("CWE-") and not value.startswith("CWE-NVD"):
                    cwe_ids.append(value)

        # Build the NVD URL for this CVE so agents can include it as a reference.
        cve_id = cve.get("id", "")
        nvd_url = f"https://nvd.nist.gov/vuln/detail/{cve_id}" if cve_id else None

        cves.append({
            "cve_id":      cve_id,
            # e.g. "CVE-2024-12345"
            "description": description,
            # English description from NVD
            "severity":    severity,
            # "CRITICAL", "HIGH", "MEDIUM", "LOW", or "N/A"
            "cvss_score":  cvss_score,
            # CVSS v3 base score e.g. 9.8, or None if not available
            "published":   cve.get("published", "")[:10],
            # Publication date truncated to YYYY-MM-DD
            "cwe_ids":     list(set(cwe_ids)),
            # Deduplicated list of associated CWE IDs
            "nvd_url":     nvd_url,
            # Direct link to the NVD entry for citation
        })

    return {
        "cves":        cves,
        "total_found": total_found,
        "keyword":     keyword,
        "error":       None,
    }


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
                "Searches the NIST National Vulnerability Database (NVD) for "
                "recent CVEs matching a keyword. Returns CVE IDs, descriptions, "
                "CVSS severity scores, associated CWE IDs, and NVD links. "
                "Use this to ground a threat model in real, published vulnerabilities."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keyword": {
                        "type": "string",
                        "description": (
                            "Search term for the CVE query. Use security-relevant "
                            "terms related to the coding task, e.g. 'SQL injection', "
                            "'path traversal', 'authentication bypass'."
                        ),
                    },
                    "max_results": {
                        "type": "integer",
                        "description": f"Number of CVEs to return (default {MAX_RESULTS}, max {MAX_CAP}).",
                        "default": MAX_RESULTS,
                    },
                },
                "required": ["keyword"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Handles a tool call from an agent.

    Validates the tool name, extracts arguments, calls the NVD API,
    and returns the result as a JSON string wrapped in TextContent.
    """
    if name != TOOL_NAME:
        raise ValueError(
            f"Unknown tool '{name}'. This server only exposes '{TOOL_NAME}'."
        )

    keyword     = arguments.get("keyword", "").strip()
    max_results = int(arguments.get("max_results", MAX_RESULTS))

    if not keyword:
        result = {
            "cves": [], "total_found": 0, "keyword": "",
            "error": "No keyword provided.",
        }
    else:
        result = await _search_nvd(keyword, max_results)

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
    Tests the NVD API integration directly without the MCP protocol.

    Run with: python mcp_servers/nist_nvd_server.py --test

    Searches for 'SQL injection' CVEs so you can verify the API is reachable
    and the response is being parsed correctly before wiring into agents.
    """
    keyword = "SQL injection Python"
    print(f"Searching NVD for: '{keyword}' (max 3 results)...\n")

    result = await _search_nvd(keyword, max_results=3)

    if result["error"]:
        print(f"Error: {result['error']}")
        return

    print(f"Total matching CVEs in NVD: {result['total_found']}")
    print(f"Returned: {len(result['cves'])}\n")

    for cve in result["cves"]:
        print(f"  {cve['cve_id']} | {cve['severity']} | Score: {cve['cvss_score']}")
        print(f"  CWEs: {cve['cwe_ids'] or 'None listed'}")
        print(f"  Published: {cve['published']}")
        print(f"  {cve['description'][:120]}...")
        print(f"  {cve['nvd_url']}")
        print()


if __name__ == "__main__":
    if "--test" in sys.argv:
        asyncio.run(_run_test())
    else:
        asyncio.run(_serve())
