"""Fetch any URL directly, with browser-like headers to get past naive bot
filters (missing/!browser User-Agent, missing Accept headers, etc.).

Uses the system `curl` (better TLS/HTTP-2/compression than urllib, so it looks
more like a real browser), falling back to urllib if curl is unavailable. No
proxy or third-party reader is involved — requests go straight to the target.

This defeats *header-based* blocking (the common case, e.g. IGN 403, Game8 202)
and does not consult robots.txt (a reader acting on the user's behalf, like the
browser they'd open themselves). It does NOT solve interactive JS challenges
(full Cloudflare "checking your browser") or CAPTCHAs — those need a real browser
engine and are deliberately out of scope. We surface the HTTP status honestly.
"""

import re
import shutil
import subprocess
import urllib.request

# A current desktop Chrome on Windows.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}

# curl appends this after the body via -w, so we can read status + content-type
# without mixing response headers into the body. Distinctive enough not to clash.
_SEP = b"\n__NETLENS_META__\t"

_META_CHARSET_RE = re.compile(
    rb"""<meta[^>]+charset=["']?\s*([a-zA-Z0-9_\-]+)""", re.I
)
_CT_CHARSET_RE = re.compile(r"charset=([a-zA-Z0-9_\-]+)", re.I)


def _charset_from(content_type: str, head: bytes) -> str:
    """Best-effort charset: Content-Type header first, then an HTML <meta>, else utf-8."""
    m = _CT_CHARSET_RE.search(content_type or "")
    if m:
        return m.group(1)
    m = _META_CHARSET_RE.search(head[:4096])
    if m:
        try:
            return m.group(1).decode("ascii")
        except UnicodeDecodeError:
            pass
    return "utf-8"


def _decode(body: bytes, content_type: str) -> str:
    charset = _charset_from(content_type, body)
    try:
        return body.decode(charset, "replace")
    except (LookupError, TypeError):
        return body.decode("utf-8", "replace")


def _via_curl(url: str, timeout: int, max_bytes: int | None):
    curl = shutil.which("curl")
    if not curl:
        return None
    cmd = [curl, "-sSL", "--compressed", "--max-time", str(timeout), "-A", USER_AGENT]
    for k, v in HEADERS.items():
        cmd += ["-H", f"{k}: {v}"]
    # write-out (parsed by us) is appended after the body on stdout.
    cmd += ["-w", "\\n__NETLENS_META__\\t%{http_code}\\t%{content_type}", url]
    proc = subprocess.run(cmd, capture_output=True)  # binary; we decode ourselves
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"curl error ({proc.returncode}): {err or 'request failed'}")

    raw = proc.stdout
    status: int | None = None
    content_type = ""
    idx = raw.rfind(_SEP)
    if idx != -1:
        meta = raw[idx + len(_SEP):].decode("utf-8", "replace")
        raw = raw[:idx]
        parts = meta.split("\t")
        if parts and parts[0].strip().isdigit():
            status = int(parts[0].strip())
        if len(parts) > 1:
            content_type = parts[1].strip()

    truncated = False
    if max_bytes is not None and len(raw) > max_bytes:
        raw = raw[:max_bytes]
        truncated = True
    return _decode(raw, content_type), status, content_type, truncated


def _via_urllib(url: str, timeout: int, max_bytes: int | None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **HEADERS})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        content_type = resp.headers.get("Content-Type", "")
        raw = resp.read() if max_bytes is None else resp.read(max_bytes)
        truncated = max_bytes is not None and len(raw) == max_bytes
        status = getattr(resp, "status", None)
    return _decode(raw, content_type), status, content_type, truncated


def fetch(url: str, timeout: int = 30, max_bytes: int | None = None) -> dict:
    """Fetch a URL with browser-like headers.

    Returns {url, status, content_type, html, truncated}. `status` is the HTTP
    status (or None if the transport couldn't report one); callers should check
    it rather than assume success.
    """
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    result = _via_curl(url, timeout, max_bytes)
    if result is None:
        result = _via_urllib(url, timeout, max_bytes)
    html, status, content_type, truncated = result
    return {
        "url": url,
        "status": status,
        "content_type": content_type,
        "html": html,
        "truncated": truncated,
    }
