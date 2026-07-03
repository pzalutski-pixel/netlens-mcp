"""Tests for search-result parsing, engine selection, and fallback."""

import base64
import json

from netlens_mcp import search


def _bing_href(real_url: str) -> str:
    token = base64.urlsafe_b64encode(real_url.encode()).decode().rstrip("=")
    return f"https://www.bing.com/ck/a?!&amp;&amp;p=abc&amp;u=a1{token}&amp;ntb=1"

DDG_HTML = """
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=x">First <b>Result</b></a>
  <a class="result__snippet" href="#">Snippet one.</a>
</div>
<div class="result">
  <a class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fb">Second Result</a>
  <a class="result__snippet" href="#">Snippet two.</a>
</div>
"""

# Real Bing markup: multi-class b_algo, <h2> with attributes, base64 redirect href.
BING_HTML = (
    '<li class="b_algo"><h2 class="b_topTitle">'
    f'<a href="{_bing_href("https://example.com/a")}">Bing A</a></h2>'
    '<p class="b_lineclamp2">Bing snippet A.</p></li>'
    '<li class="b_algo b_algoBigWiki">'
    f'<h2><a href="{_bing_href("https://example.com/b")}">Bing B</a></h2>'
    '<p>Bing snippet B.</p></li>'
)

# Real Mojeek markup: <li class="rN"> with <h2><a href="REAL_URL">.
MOJEEK_HTML = """
<ul class="results-standard">
  <li class="r1"><h2><a href="https://example.com/a">Mojeek A</a></h2><p class="s">Mojeek snippet A.</p></li>
  <li class="r2"><h2><a href="https://example.com/b">Mojeek B</a></h2><p class="s">Mojeek snippet B.</p></li>
</ul>
"""


def test_parse_ddg_decodes_wrapped_urls_and_snippets():
    r = search._parse_ddg(DDG_HTML, 8)
    assert r[0]["url"] == "https://example.com/a"
    assert r[0]["title"] == "First Result"
    assert r[0]["snippet"] == "Snippet one."
    assert r[1]["url"] == "https://example.com/b"


def test_parse_ddg_respects_limit():
    assert len(search._parse_ddg(DDG_HTML, 1)) == 1


def test_parse_bing_decodes_redirect_urls():
    r = search._parse_bing(BING_HTML, 8)
    assert [x["url"] for x in r] == ["https://example.com/a", "https://example.com/b"]
    assert r[0]["title"] == "Bing A"
    assert r[0]["snippet"] == "Bing snippet A."


def test_bing_real_url_passthrough_when_not_redirect():
    assert search._bing_real_url("https://plain.example.com/x") == "https://plain.example.com/x"


def test_parse_mojeek():
    r = search._parse_mojeek(MOJEEK_HTML, 8)
    assert r[0]["title"] == "Mojeek A"
    assert r[0]["url"] == "https://example.com/a"
    assert r[0]["snippet"] == "Mojeek snippet A."


def test_resolve_order_defaults_to_chain(monkeypatch):
    monkeypatch.delenv("NETLENS_SEARCH_ENGINE", raising=False)
    monkeypatch.delenv("NETLENS_SEARXNG_URL", raising=False)
    assert search._resolve_order(None) == search.DEFAULT_ORDER


def test_resolve_order_specific_engine():
    assert search._resolve_order("bing") == ("bing",)


def test_resolve_order_env_default(monkeypatch):
    monkeypatch.setenv("NETLENS_SEARCH_ENGINE", "mojeek")
    assert search._resolve_order(None) == ("mojeek",)


def test_resolve_order_prefers_searxng_when_configured(monkeypatch):
    monkeypatch.delenv("NETLENS_SEARCH_ENGINE", raising=False)
    monkeypatch.setenv("NETLENS_SEARXNG_URL", "https://searx.example.org")
    assert search._resolve_order("auto") == ("searxng", *search.DEFAULT_ORDER)


def test_search_falls_through_to_next_engine(monkeypatch):
    calls = []

    def fake_run(name, query, limit):
        calls.append(name)
        return [] if name == "duckduckgo" else [{"title": "hit", "url": "u", "snippet": ""}]

    monkeypatch.setattr(search, "_run_engine", fake_run)
    monkeypatch.delenv("NETLENS_SEARXNG_URL", raising=False)
    monkeypatch.delenv("NETLENS_SEARCH_ENGINE", raising=False)
    out = search.search("q")
    assert out and out[0]["title"] == "hit"
    assert calls == ["duckduckgo", "mojeek"]  # order is ddg -> mojeek -> bing; stops at mojeek


def test_searxng_parses_json(monkeypatch):
    monkeypatch.setenv("NETLENS_SEARXNG_URL", "https://searx.example.org")
    payload = {"results": [{"title": "SX", "url": "https://ex.com", "content": "sx snippet"}]}
    monkeypatch.setattr(search.fetcher, "fetch", lambda url, **k: {"status": 200, "html": json.dumps(payload)})
    r = search._searxng("q", 8)
    assert r == [{"title": "SX", "url": "https://ex.com", "snippet": "sx snippet"}]


def test_engine_error_status_yields_no_results(monkeypatch):
    monkeypatch.setattr(search.fetcher, "fetch", lambda url, **k: {"status": 503, "html": "nope"})
    assert search._run_engine("duckduckgo", "q", 8) == []
