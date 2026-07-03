# netlens-mcp

[![npm](https://img.shields.io/npm/v/netlens-mcp.svg)](https://www.npmjs.com/package/netlens-mcp)
[![PyPI](https://img.shields.io/pypi/v/netlens-mcp.svg)](https://pypi.org/project/netlens-mcp/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://github.com/pzalutski-pixel/netlens-mcp/blob/main/LICENSE)

An MCP server for **unobstructed web reading**: it fetches any URL directly with
browser-like headers — past `robots.txt` and naive bot blocks — and returns the
**full page** as clean, ad-stripped Markdown, not a summary.

## Requirements

- **Python 3.10+** installed and on PATH

## Quick Start

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

## What This Package Does

This npm package bundles the full NetLens server (pure Python, no pip install and
no network dependency after install). It:

1. Checks that Python 3.10+ is installed
2. Launches the bundled MCP server over stdio

Zero external Python dependencies — the server uses only the standard library.

## Tools

- **`web_search`** — search the web and get real result links (title/URL/snippet),
  not summaries. Selectable engine (DuckDuckGo → Bing → Mojeek, or SearXNG).
- **`web_fetch`** — fetch any page as full, clean Markdown. Modes: `article`
  (main content, default), `full` (whole body), `raw` (HTML).

## Configuration

| Environment Variable | Default | Description |
|---|---|---|
| `NETLENS_SEARCH_ENGINE` | `auto` | Default search backend: `auto`, `duckduckgo`, `bing`, `mojeek`, `searxng` |
| `NETLENS_SEARXNG_URL` | — | Base URL of a SearXNG instance for `engine=searxng` |

## Documentation

Full documentation and tool reference: [GitHub](https://github.com/pzalutski-pixel/netlens-mcp)
