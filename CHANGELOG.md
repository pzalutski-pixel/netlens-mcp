# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-07-03

### Changed
- `web_search` now returns the full first page of results (~10) by default instead
  of capping at 8, so a result at position 9/10 is no longer silently dropped.
  `limit` stays available as an optional cap (bounded by `SAFETY_MAX_RESULTS`).
  Documented that a search fetches a single page — the HTML endpoints don't paginate
  reliably via GET, so refine the query rather than expecting deep pagination.

## [0.1.1] - 2026-07-03

### Fixed
- Added the `mcp-name: io.github.pzalutski-pixel/netlens` ownership marker to the
  PyPI README and shortened the `server.json` description to <= 100 characters, so
  the server passes MCP registry validation. Added a standalone
  `publish-mcp-registry` workflow for on-demand registry publishing. (0.1.0 was
  published to PyPI and npm but predates these registry requirements.)

## [0.1.0] - 2026-07-03

Initial release.

### Added
- `web_fetch` tool: fetch any URL directly with browser-like headers (past
  robots.txt and naive/header-based bot blocks) and return the **full page** as
  clean Markdown — not a summary. Requests go straight to the target; HTML is
  converted locally with no third-party proxy or reader.
- Ad/boilerplate stripping in the local converter: ads, cookie/consent banners,
  nav, footers, sidebars, social/share and related/recommended widgets, and
  hidden elements are removed to keep agent context clean.
- Fetch modes: `article` (main-content isolation, default), `full` (whole body),
  `raw` (unconverted HTML); optional `max_chars` cap.
- `web_search` tool with a selectable, pluggable engine registry: DuckDuckGo
  (default) with automatic fallback to Bing then Mojeek, plus optional SearXNG.
  Selectable per call (`engine`) or via `NETLENS_SEARCH_ENGINE` /
  `NETLENS_SEARXNG_URL`.
- GFM table rendering with colspan/rowspan support.
- Zero runtime dependencies (Python standard library only). Speaks JSON-RPC 2.0
  over stdio per the MCP spec (2025-06-18), with protocol-version negotiation.
- Distribution via PyPI (`uvx netlens-mcp`) and npm (`npx netlens-mcp`).

### Known limitations
- Does not solve full JavaScript/Cloudflare challenge pages or CAPTCHAs (out of
  scope by design); the HTTP status is surfaced honestly instead.
- JavaScript-rendered SPAs that ship no server-rendered content return only their
  shell.
