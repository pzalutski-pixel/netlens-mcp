# NetLens

[![npm](https://img.shields.io/npm/v/netlens-mcp.svg)](https://www.npmjs.com/package/netlens-mcp)
[![PyPI](https://img.shields.io/pypi/v/netlens-mcp.svg)](https://pypi.org/project/netlens-mcp/)
[![CI](https://github.com/pzalutski-pixel/netlens-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/pzalutski-pixel/netlens-mcp/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

An MCP server for **unobstructed web reading**. It fetches any URL directly with
browser-like headers — past `robots.txt` and naive bot blocks — and returns the
**full page** as clean, ad-stripped Markdown, not a summary. Plus web search that
returns real links. Zero dependencies: pure Python standard library.

## Built for AI Agents

AI agents constantly hit pages their built-in tools can't read. NetLens fixes the
three usual reasons a fetch comes back empty or useless:

| Native web tools | NetLens |
|---|---|
| Honor `robots.txt`, so crawler-disallowed pages return nothing | Reads like the browser you'd open yourself — doesn't consult `robots.txt` |
| Blocked by header/User-Agent bot filters (`403`/`202` to non-browser clients) | Sends real browser headers via the system `curl`; commonly turns `403 → 200` |
| Return a **summary** of the page | Returns the **full** page content as Markdown |
| Leave ads, cookie banners, nav, and related-links chrome in the output | Strips boilerplate locally so only the content reaches your context |

It does **not** try to defeat JavaScript/Cloudflare challenge pages or CAPTCHAs —
that's out of scope by design. When a page is a hard block, the HTTP status is
surfaced honestly rather than faked.

## Installation

**npm (via npx):**

```json
{
  "mcpServers": {
    "netlens": {
      "command": "npx",
      "args": ["-y", "netlens-mcp"]
    }
  }
}
```

**PyPI (via uvx):**

```json
{
  "mcpServers": {
    "netlens": {
      "command": "uvx",
      "args": ["netlens-mcp"]
    }
  }
}
```

Add either to your MCP client config (e.g. `.mcp.json` for Claude Code), then
restart the session so the tools load.

## Tools

### `web_search`

Search the web and return real result links (title, URL, snippet), parsed locally —
**links, not summaries**. Follow up with `web_fetch` to read a result.

| Argument | Type | Description |
|---|---|---|
| `query` | string (required) | The search query |
| `limit` | integer | Max results (default 8) |
| `engine` | string | `auto` (default), `duckduckgo`, `bing`, `mojeek`, `searxng` |

### `web_fetch`

Fetch any page and return its full content as clean Markdown.

| Argument | Type | Description |
|---|---|---|
| `url` | string (required) | URL to fetch (scheme optional; `https` assumed) |
| `mode` | string | `article` (main content only, default), `full` (whole body), `raw` (unconverted HTML) |
| `max_chars` | integer | Optional cap on returned characters (truncates with a note) |

**Workflow:** `web_search` to find pages, then `web_fetch` to read them.

## Search engines

Search is a pluggable, selectable registry. In `auto` mode NetLens tries engines in
order and returns the first with results, so a rate-limit/challenge page on one
falls through to the next.

| Engine | Notes |
|---|---|
| `duckduckgo` | Default; `html.duckduckgo.com` endpoint |
| `bing` | Automatic fallback |
| `mojeek` | Independent index; automatic fallback |
| `searxng` | Self-hosted/public SearXNG JSON API — set `NETLENS_SEARXNG_URL` |

Pick per call with the `engine` argument, or set a default with
`NETLENS_SEARCH_ENGINE`.

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `NETLENS_SEARCH_ENGINE` | `auto` | Default search backend |
| `NETLENS_SEARXNG_URL` | — | SearXNG base URL for `engine=searxng` |

## How it works

- **Direct fetch.** Requests go straight to the target site via the system `curl`
  (better TLS/HTTP-2/compression, so it looks like a real browser), falling back to
  `urllib`. No third-party proxy or reader is involved.
- **Local conversion.** HTML → Markdown happens in-process with a hand-rolled
  `html.parser` converter — headings, lists, links (relative URLs resolved), code
  blocks, and GFM tables with colspan/rowspan.
- **Boilerplate stripping.** Ads, cookie/consent banners, nav, footers, sidebars,
  social/share and related/recommended widgets, and hidden elements are removed. In
  `article` mode NetLens also isolates the main content region (`<main>` /
  `<article>` / `[role=main]`).
- **Response charset** is honored (from `Content-Type` or `<meta>`), so non-UTF-8
  pages don't come back garbled.

## Usage from the CLI

The server is also a plain script — handy for testing before a client loads it:

```sh
python -m netlens_mcp.server search "best bg3 starting class"
python -m netlens_mcp.server fetch  https://www.ign.com/wikis/baldurs-gate-3
python -m netlens_mcp.server full   https://example.com   # whole body
python -m netlens_mcp.server raw    https://example.com   # unconverted HTML
```

`python -m netlens_mcp` runs the stdio MCP server; `python -m netlens_mcp.server
<cmd>` runs the CLI.

## Development

```sh
pip install -e ".[dev]"
python -m pytest        # run the test suite
ruff check .            # lint
```

## Requirements

- Python 3.10+ (and the system `curl`, which ships with modern Windows/macOS/Linux;
  falls back to `urllib` if absent)

## License

Apache License 2.0 — see [LICENSE](LICENSE) and [NOTICE](NOTICE).

<!-- mcp-name: io.github.pzalutski-pixel/netlens -->

