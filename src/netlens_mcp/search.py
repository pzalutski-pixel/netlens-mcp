"""Web search via HTML search endpoints, fetched directly through our own
bot-bypassing fetcher. Returns real result links (and snippets) parsed locally —
NOT summarized. Pair with web_fetch to read the full page content.

Engines are pluggable and selectable:

* ``auto`` (default) tries each engine in DEFAULT_ORDER and returns the first
  that yields results — so a rate-limit/challenge page on one falls through to
  the next.
* A specific engine can be forced by name (``duckduckgo``, ``bing``, ``mojeek``,
  ``searxng``), via the web_search ``engine`` argument or the
  ``NETLENS_SEARCH_ENGINE`` environment variable.
* ``searxng`` targets a self-hosted/public SearXNG JSON endpoint set via
  ``NETLENS_SEARXNG_URL`` (e.g. https://searx.example.org); when configured it is
  also tried first in ``auto`` mode.

Adding an engine is a small, local change: write a ``_parse_<engine>`` and a URL
builder, then register it in ENGINES.
"""

import base64
import json
import os
import re
import urllib.parse
from html import unescape

from netlens_mcp import fetcher

DDG_HTML = "https://html.duckduckgo.com/html/"
BING_HTML = "https://www.bing.com/search"
MOJEEK_HTML = "https://www.mojeek.com/search"

# Mojeek before Bing: Mojeek returns real URLs in simple markup, while Bing wraps
# every result in a base64 redirect that's more fragile to decode.
DEFAULT_ORDER = ("duckduckgo", "mojeek", "bing")


def _strip_tags(s: str) -> str:
    return unescape(re.sub(r"<[^>]+>", "", s)).strip()


def _q(query: str) -> str:
    return urllib.parse.urlencode({"q": query})


# --- DuckDuckGo (html.duckduckgo.com/html) ---------------------------------

def _ddg_real_url(href: str) -> str:
    """DuckDuckGo wraps results as //duckduckgo.com/l/?uddg=<encoded real url>."""
    if "uddg=" in href:
        encoded = href.split("uddg=", 1)[1].split("&", 1)[0]
        return urllib.parse.unquote(encoded)
    if href.startswith("//"):
        return "https:" + href
    return href


def _parse_ddg(html: str, limit: int) -> list[dict]:
    results: list[dict] = []
    for m in re.finditer(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.S):
        results.append({"title": _strip_tags(m.group(2)), "url": _ddg_real_url(m.group(1)), "snippet": ""})
        if len(results) >= limit:
            break
    snippets = [
        _strip_tags(m.group(1))
        for m in re.finditer(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
    ]
    for i, snippet in enumerate(snippets):
        if i < len(results):
            results[i]["snippet"] = snippet
    return results[:limit]


# --- Bing (www.bing.com/search) --------------------------------------------

def _bing_real_url(href: str) -> str:
    """Bing wraps results as /ck/a?...&u=a1<base64url-of-real-url>&ntb=1."""
    m = re.search(r"[?&]u=a1([^&]+)", href)
    if not m:
        return href
    token = m.group(1)
    token += "=" * (-len(token) % 4)  # restore base64 padding
    try:
        return base64.urlsafe_b64decode(token).decode("utf-8", "replace")
    except (ValueError, TypeError):
        return href


def _parse_bing(html: str, limit: int) -> list[dict]:
    results: list[dict] = []
    for block in re.finditer(r"<li[^>]*\bb_algo\b[^>]*>(.*?)</li>", html, re.S):
        chunk = block.group(1)
        link = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', chunk, re.S)
        if not link:
            continue
        snip = re.search(r"<p[^>]*>(.*?)</p>", chunk, re.S)
        results.append({
            "title": _strip_tags(link.group(2)),
            "url": _bing_real_url(unescape(link.group(1))),
            "snippet": _strip_tags(snip.group(1)) if snip else "",
        })
        if len(results) >= limit:
            break
    return results[:limit]


# --- Mojeek (www.mojeek.com/search) ----------------------------------------

def _parse_mojeek(html: str, limit: int) -> list[dict]:
    results: list[dict] = []
    for block in re.finditer(r"<li[^>]*>(.*?)</li>", html, re.S):
        chunk = block.group(1)
        link = re.search(r'<h2[^>]*>\s*<a[^>]+href="(https?://[^"]+)"[^>]*>(.*?)</a>', chunk, re.S)
        if not link:
            continue
        snip = (re.search(r'<p[^>]*class="[^"]*\bs\b[^"]*"[^>]*>(.*?)</p>', chunk, re.S)
                or re.search(r"<p[^>]*>(.*?)</p>", chunk, re.S))
        results.append({
            "title": _strip_tags(link.group(2)),
            "url": link.group(1),
            "snippet": _strip_tags(snip.group(1)) if snip else "",
        })
        if len(results) >= limit:
            break
    return results[:limit]


# (build_url(query) -> url, parse(html, limit) -> results)
ENGINES = {
    "duckduckgo": (lambda q: DDG_HTML + "?" + _q(q), _parse_ddg),
    "bing": (lambda q: BING_HTML + "?" + _q(q), _parse_bing),
    "mojeek": (lambda q: MOJEEK_HTML + "?" + _q(q), _parse_mojeek),
}


def _searxng(query: str, limit: int) -> list[dict]:
    """Query a SearXNG JSON endpoint (URL from NETLENS_SEARXNG_URL)."""
    base = os.environ.get("NETLENS_SEARXNG_URL")
    if not base:
        return []
    url = base.rstrip("/") + "/search?" + urllib.parse.urlencode({"q": query, "format": "json"})
    res = fetcher.fetch(url)
    if res.get("status") and res["status"] >= 400:
        return []
    try:
        data = json.loads(res["html"])
    except (ValueError, TypeError):
        return []
    return [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("content", "")}
        for r in data.get("results", [])[:limit]
    ]


def _run_engine(name: str, query: str, limit: int) -> list[dict]:
    if name == "searxng":
        return _searxng(query, limit)
    build, parse = ENGINES[name]
    res = fetcher.fetch(build(query))
    if res.get("status") and res["status"] >= 400:
        return []
    return parse(res["html"], limit)


def available_engines() -> list[str]:
    engines = ["auto", *ENGINES.keys()]
    if os.environ.get("NETLENS_SEARXNG_URL"):
        engines.append("searxng")
    return engines


def _resolve_order(engine: str | None) -> tuple[str, ...]:
    engine = (engine or os.environ.get("NETLENS_SEARCH_ENGINE") or "auto").lower()
    if engine == "searxng" or engine in ENGINES:
        return (engine,)
    # auto (or anything unrecognized): try SearXNG first if configured, then the chain.
    if os.environ.get("NETLENS_SEARXNG_URL"):
        return ("searxng", *DEFAULT_ORDER)
    return DEFAULT_ORDER


def search(query: str, limit: int = 8, engine: str | None = None) -> list[dict]:
    """Search the web and return [{title, url, snippet}].

    `engine` selects the backend (default: auto-fallback chain). Falls through to
    the next engine when one errors or yields no results.
    """
    for name in _resolve_order(engine):
        results = _run_engine(name, query, limit)
        if results:
            return results
    return []
