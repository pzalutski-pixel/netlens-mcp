"""netlens-mcp: MCP server for unobstructed web reading.

Searches the web and fetches any URL directly with browser-like headers (to get
past naive bot filters), returning FULL page content as clean Markdown — not a
summary. Conversion happens locally; no third-party proxy or reader. Speaks
JSON-RPC 2.0 over stdio per the MCP spec (2025-06-18), zero-dependency (stdlib
only). Also runnable as a CLI:

    python -m netlens_mcp.server search  "best bg3 starting class"
    python -m netlens_mcp.server fetch   https://www.ign.com/wikis/baldurs-gate-3
    python -m netlens_mcp.server full    https://example.com   # whole body, keep chrome
    python -m netlens_mcp.server raw     https://example.com   # unconverted HTML
"""

import asyncio
import json
import sys
from typing import Any

from netlens_mcp import __version__, convert, fetcher, search

# Protocol revisions we implement, newest first. We negotiate against these: if
# the client asks for one we support we echo it, otherwise we return our latest.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]

SERVER_INSTRUCTIONS = (
    "Read web pages that Anthropic's native tools can't: this fetches URLs directly "
    "with browser-like headers (past robots.txt and naive bot blocks) and returns the "
    "FULL page as clean Markdown, not a summary. Use web_search to find pages, then "
    "web_fetch to read them. It does not solve JS/Cloudflare challenge pages or CAPTCHAs."
)

# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------


def write_message(data: dict) -> None:
    # json.dumps escapes embedded newlines and non-ASCII, so the serialized line
    # is a single newline-delimited MCP message per the stdio transport rules.
    sys.stdout.buffer.write((json.dumps(data) + "\n").encode("utf-8"))
    sys.stdout.buffer.flush()


def jsonrpc_response(req_id: Any, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def jsonrpc_error(req_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def tool_result(text: str, is_error: bool = False) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

# Read-only (no side effects) and open-world (reach out to the live internet).
_READ_WEB = {"readOnlyHint": True, "openWorldHint": True}

TOOLS = [
    {
        "name": "web_search",
        "title": "Web Search",
        "description": (
            "Search the web and return real result links (title, URL, snippet), "
            "parsed locally from a search engine's HTML endpoint via a direct, "
            "bot-bypassing fetch. Returns LINKS, not summaries — follow up with "
            "web_fetch to read a result's full content. WORKFLOW: web_search to find "
            "pages, then web_fetch to read them."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "limit": {"type": "integer", "description": "Max results (default 8)"},
                "engine": {
                    "type": "string",
                    "enum": ["auto", "duckduckgo", "bing", "mojeek", "searxng"],
                    "description": (
                        "Search backend (default 'auto' = try DuckDuckGo, then Bing, then Mojeek). "
                        "'searxng' needs NETLENS_SEARXNG_URL set to a SearXNG instance."
                    ),
                },
            },
            "required": ["query"],
        },
        "annotations": _READ_WEB,
    },
    {
        "name": "web_fetch",
        "title": "Web Fetch (full page)",
        "description": (
            "Fetch ANY web page directly and return its FULL content as clean Markdown "
            "(not a summary). Uses browser-like headers to get past common bot filters "
            "that block naive/robots-respecting clients (e.g. 403/202 to non-browser "
            "clients). Requests go straight to the target site; HTML is converted to "
            "Markdown locally (no third-party proxy/reader). Ads, cookie/consent "
            "banners, nav, and social/related widgets are stripped to keep context "
            "clean. mode='article' (default) isolates the main content; mode='full' "
            "keeps the whole page body; mode='raw' returns unconverted HTML. Does NOT "
            "solve full JS/Cloudflare challenge pages or CAPTCHAs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch (scheme optional; https assumed)"},
                "mode": {
                    "type": "string",
                    "enum": ["article", "full", "raw"],
                    "description": "article=main content only (default), full=whole body, raw=unconverted HTML",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Optional cap on returned characters (truncates with a note); omit for full content",
                },
            },
            "required": ["url"],
        },
        "annotations": _READ_WEB,
    },
]

KNOWN_TOOLS = {t["name"] for t in TOOLS}


# ---------------------------------------------------------------------------
# Tool dispatch (blocking I/O runs in a thread to keep the loop responsive)
# ---------------------------------------------------------------------------


def _cap(text: str, max_chars: int | None) -> str:
    if max_chars and len(text) > max_chars:
        return text[:max_chars] + f"\n\n_(truncated at {max_chars} characters)_"
    return text


async def handle_tool_call(name: str, arguments: dict) -> dict:
    """Run a tool. Execution failures are returned as isError results (per spec);
    an unknown tool name is handled as a protocol error by the router instead."""
    loop = asyncio.get_event_loop()
    try:
        if name == "web_search":
            query = arguments["query"]
            limit = int(arguments.get("limit", 8))
            engine = arguments.get("engine")
            results = await loop.run_in_executor(None, lambda: search.search(query, limit, engine))
            if not results:
                return tool_result(f"No results for: {query}")
            return tool_result(json.dumps(results, indent=2))

        if name == "web_fetch":
            url = arguments["url"]
            mode = arguments.get("mode", "article")
            max_chars = arguments.get("max_chars")
            max_chars = int(max_chars) if max_chars else None

            res = await loop.run_in_executor(None, lambda: fetcher.fetch(url))
            status = res.get("status")
            warn = "" if (status is None or status < 400) else f"_(warning: HTTP {status})_\n\n"

            if mode == "raw":
                body = f"<!-- {res['url']} (HTTP {status}) -->\n" + res["html"]
                return tool_result(_cap(body, max_chars))

            page = convert.page_to_markdown(res["html"], res["url"], mode=mode)
            return tool_result(_cap(warn + page["markdown"], max_chars))

        # Unreachable: router validates the name first.
        return tool_result(json.dumps({"error": f"Unknown tool: {name}"}), is_error=True)

    except Exception as e:
        return tool_result(json.dumps({"error": str(e), "tool": name}), is_error=True)


# ---------------------------------------------------------------------------
# MCP request router
# ---------------------------------------------------------------------------


def _negotiate_version(requested: Any) -> str:
    if isinstance(requested, str) and requested in SUPPORTED_PROTOCOL_VERSIONS:
        return requested
    return LATEST_PROTOCOL_VERSION


async def handle_request(msg: dict) -> dict | None:
    method = msg.get("method", "")
    req_id = msg.get("id")
    params = msg.get("params") or {}

    if req_id is None:
        return None  # a notification (e.g. notifications/initialized); nothing to return

    if method == "initialize":
        return jsonrpc_response(req_id, {
            "protocolVersion": _negotiate_version(params.get("protocolVersion")),
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "netlens-mcp", "title": "NetLens", "version": __version__},
            "instructions": SERVER_INSTRUCTIONS,
        })
    if method == "ping":
        return jsonrpc_response(req_id, {})
    if method == "tools/list":
        return jsonrpc_response(req_id, {"tools": TOOLS})
    if method == "tools/call":
        name = params.get("name", "")
        if name not in KNOWN_TOOLS:
            return jsonrpc_error(req_id, -32602, f"Unknown tool: {name}")
        result = await handle_tool_call(name, params.get("arguments") or {})
        return jsonrpc_response(req_id, result)

    return jsonrpc_error(req_id, -32601, f"Method not found: {method}")


# ---------------------------------------------------------------------------
# stdio server loop (resilient: one bad message never kills the server)
# ---------------------------------------------------------------------------


async def _read_line() -> bytes:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, sys.stdin.buffer.readline)


async def main():
    while True:
        raw = await _read_line()
        if not raw:
            break  # EOF: client closed stdin, shut down
        text = raw.strip()
        if not text:
            continue

        try:
            msg = json.loads(text.decode("utf-8-sig"))
        except (ValueError, UnicodeDecodeError):
            write_message(jsonrpc_error(None, -32700, "Parse error"))
            continue

        try:
            response = await handle_request(msg)
        except Exception as e:  # never let a handler crash the loop
            req_id = msg.get("id") if isinstance(msg, dict) else None
            write_message(jsonrpc_error(req_id, -32603, f"Internal error: {e}"))
            continue

        if response is not None:
            write_message(response)


# ---------------------------------------------------------------------------
# CLI mode (usable immediately, before the MCP is loaded into a session)
# ---------------------------------------------------------------------------


def _cli(argv: list[str]) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if not argv:
        print("usage: netlens_mcp.server <search|fetch|full|raw> <args...>", file=sys.stderr)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "search":
        for r in search.search(" ".join(rest)):
            line = f"- {r['title']} -> {r['url']}"
            if r.get("snippet"):
                line += f"\n    {r['snippet']}"
            print(line)
        return 0
    if cmd in ("fetch", "full", "raw"):
        if not rest:
            print(f"usage: netlens_mcp.server {cmd} <url>", file=sys.stderr)
            return 2
        res = fetcher.fetch(rest[0])
        if cmd == "raw":
            print(f"<!-- {res['url']} (HTTP {res['status']}) -->")
            print(res["html"])
        else:
            mode = "article" if cmd == "fetch" else "full"
            print(convert.page_to_markdown(res["html"], res["url"], mode=mode)["markdown"])
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 2


def main_sync():
    asyncio.run(main())


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
