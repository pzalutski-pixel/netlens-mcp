"""Tests for the MCP request router / JSON-RPC handling (spec conformance)."""

from netlens_mcp import server


def _init(version="2025-06-18"):
    return {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": version, "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}


async def test_initialize_echoes_supported_version():
    r = await server.handle_request(_init("2025-03-26"))
    assert r["result"]["protocolVersion"] == "2025-03-26"


async def test_initialize_negotiates_down_on_unsupported():
    r = await server.handle_request(_init("1.0.0"))
    assert r["result"]["protocolVersion"] == server.LATEST_PROTOCOL_VERSION


async def test_initialize_advertises_tools_and_serverinfo():
    r = await server.handle_request(_init())
    assert r["result"]["capabilities"]["tools"] == {"listChanged": False}
    assert r["result"]["serverInfo"]["name"] == "netlens-mcp"
    assert r["result"]["instructions"]


async def test_notification_returns_nothing():
    assert await server.handle_request({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None


async def test_tools_list_shape():
    r = await server.handle_request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = {t["name"]: t for t in r["result"]["tools"]}
    assert set(tools) == {"web_search", "web_fetch"}
    assert all("annotations" in t for t in tools.values())
    assert tools["web_fetch"]["inputSchema"]["properties"]["mode"]["enum"] == ["article", "full", "raw"]
    assert "searxng" in tools["web_search"]["inputSchema"]["properties"]["engine"]["enum"]


async def test_ping():
    r = await server.handle_request({"jsonrpc": "2.0", "id": 3, "method": "ping"})
    assert r["result"] == {}


async def test_unknown_tool_is_protocol_error_32602():
    r = await server.handle_request(
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "nope", "arguments": {}}})
    assert r["error"]["code"] == -32602


async def test_unknown_method_is_32601():
    r = await server.handle_request({"jsonrpc": "2.0", "id": 5, "method": "resources/list"})
    assert r["error"]["code"] == -32601


async def test_web_fetch_returns_markdown(monkeypatch):
    monkeypatch.setattr(server.fetcher, "fetch",
                        lambda url: {"url": url, "status": 200, "content_type": "text/html",
                                     "html": "<html><body><main><h1>Hi</h1><p>Body.</p></main></body></html>"})
    r = await server.handle_request({"jsonrpc": "2.0", "id": 6, "method": "tools/call",
                                     "params": {"name": "web_fetch", "arguments": {"url": "example.com"}}})
    result = r["result"]
    assert result["isError"] is False
    text = result["content"][0]["text"]
    assert "# Hi" in text and "Body." in text


async def test_web_fetch_warns_on_http_error(monkeypatch):
    monkeypatch.setattr(server.fetcher, "fetch",
                        lambda url: {"url": url, "status": 404, "content_type": "text/html",
                                     "html": "<html><body><main><p>Not found page.</p></main></body></html>"})
    r = await server.handle_request({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                     "params": {"name": "web_fetch", "arguments": {"url": "example.com"}}})
    assert "HTTP 404" in r["result"]["content"][0]["text"]


async def test_web_fetch_max_chars_truncates(monkeypatch):
    big = "<html><body><main><p>" + ("x" * 5000) + "</p></main></body></html>"
    monkeypatch.setattr(server.fetcher, "fetch",
                        lambda url: {"url": url, "status": 200, "content_type": "text/html", "html": big})
    r = await server.handle_request({"jsonrpc": "2.0", "id": 8, "method": "tools/call",
                                     "params": {"name": "web_fetch", "arguments": {"url": "e.com", "max_chars": 200}}})
    text = r["result"]["content"][0]["text"]
    assert "truncated at 200 characters" in text


async def test_web_search_passes_engine_through(monkeypatch):
    captured = {}

    def fake_search(query, limit, engine):
        captured.update(query=query, limit=limit, engine=engine)
        return [{"title": "t", "url": "u", "snippet": "s"}]

    monkeypatch.setattr(server.search, "search", fake_search)
    r = await server.handle_request({"jsonrpc": "2.0", "id": 9, "method": "tools/call",
                                     "params": {"name": "web_search", "arguments": {"query": "hi", "engine": "bing"}}})
    # no limit given -> None (search() decides the full-page default), engine passed through
    assert captured == {"query": "hi", "limit": None, "engine": "bing"}
    assert r["result"]["isError"] is False
