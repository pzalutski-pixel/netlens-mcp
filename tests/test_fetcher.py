"""Tests for the fetcher's pure helpers and URL handling (no network)."""

from netlens_mcp import fetcher


def test_charset_from_content_type_header():
    assert fetcher._charset_from("text/html; charset=Shift_JIS", b"") == "Shift_JIS"


def test_charset_from_meta_tag_when_no_header():
    head = b'<html><head><meta charset="iso-8859-1"></head>'
    assert fetcher._charset_from("", head).lower() == "iso-8859-1"


def test_charset_defaults_to_utf8():
    assert fetcher._charset_from("", b"<html></html>") == "utf-8"


def test_decode_respects_declared_charset():
    # 'é' in latin-1 is 0xE9; decoding as utf-8 would mangle it.
    body = "café".encode("latin-1")
    assert fetcher._decode(body, "text/html; charset=latin-1") == "café"


def test_decode_bad_charset_falls_back_without_crashing():
    body = "hello".encode("utf-8")
    assert fetcher._decode(body, "text/html; charset=totally-bogus") == "hello"


def test_fetch_adds_https_scheme(monkeypatch):
    seen = {}

    def fake_curl(url, timeout, max_bytes):
        seen["url"] = url
        return ("<html>ok</html>", 200, "text/html; charset=utf-8", False)

    monkeypatch.setattr(fetcher, "_via_curl", fake_curl)
    res = fetcher.fetch("example.com/page")
    assert seen["url"] == "https://example.com/page"
    assert res["status"] == 200
    assert res["html"] == "<html>ok</html>"
    assert res["truncated"] is False


def test_fetch_falls_back_to_urllib_when_curl_absent(monkeypatch):
    monkeypatch.setattr(fetcher, "_via_curl", lambda *a: None)
    monkeypatch.setattr(fetcher, "_via_urllib", lambda url, t, mb: ("<html>via urllib</html>", 200, "text/html", False))
    res = fetcher.fetch("https://example.com")
    assert res["html"] == "<html>via urllib</html>"
