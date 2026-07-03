"""Local HTML -> Markdown conversion (stdlib html.parser only).

General-purpose: works on any web page, not just one site. Strips the junk that
pollutes an agent's context — ads, cookie/consent banners, nav, social/share
widgets, "related"/"recommended" rails, sidebars, hidden elements — plus common
wiki/article chrome. In "article" mode it also isolates the main content region
(<main>/<article>/[role=main]) so general pages drop the surrounding page frame.
Tables honour colspan/rowspan so columns stay aligned.
"""

import re
from html import unescape
from html.parser import HTMLParser

# Void elements never get an end tag; don't push them on the tag stack.
_VOID = {"br", "img", "hr", "input", "meta", "link", "col", "wbr", "source", "area"}

# Whole subtrees we never want in reader output.
SKIP_TAGS = (
    "script", "style", "noscript", "head", "nav", "footer",
    "aside", "svg", "iframe", "template", "dialog",
)
# NOTE: do NOT skip <form> — some sites (e.g. Reddit) wrap real content
# (comment bodies) inside a form, and skipping it silently drops the content.

# MediaWiki / article chrome, matched as exact class tokens.
_WIKI_SKIP = frozenset((
    "mw-editsection", "toc", "navbox", "noprint", "metadata",
    "reference", "references", "reflist", "mw-empty-elt", "mw-jump",
    "mw-references-wrap", "thumbcaption", "magnify",
))

# ARIA landmark roles that denote page frame, not content.
_BAD_ROLES = frozenset((
    "banner", "navigation", "complementary", "contentinfo", "search",
    "dialog", "alertdialog", "menu", "menubar", "menuitem", "tablist", "toolbar",
))

# Exact class/id tokens (after splitting on whitespace/-/_) that mark boilerplate.
_BAD_TOKENS = frozenset((
    "ad", "ads", "adv", "advert", "advertisement", "advertising",
    "sponsor", "sponsored", "promo", "promotion", "promoted",
    "banner", "cookie", "cookies", "consent", "gdpr",
    "newsletter", "subscribe", "subscription", "signup",
    "social", "share", "shares", "sharing",
    "related", "recommended", "recommendation", "recommendations",
    "popular", "trending", "sidebar", "widget", "widgets",
    "popup", "modal", "overlay", "lightbox",
    "pagination", "pager", "masthead", "navbar", "nav", "menu",
    "toolbar", "footer", "cta", "affix",
))

# Distinctive compound substrings — safe from false positives, matched anywhere
# in the combined class+id string.
_BAD_SUBSTRINGS = (
    "adsbygoogle", "googlesyndication", "doubleclick", "taboola", "outbrain",
    "adsystem", "ad-slot", "ad-unit", "ad-container", "ad-wrapper", "ad-banner",
    "ad-label", "gpt-ad", "dfp-", "-ad-", "sponsored-content",
    "cookie-banner", "cookie-consent", "consent-banner",
    "newsletter-signup", "social-share", "share-button",
    "related-post", "related-article", "recommended-for-you", "read-more",
    "sr-only", "visually-hidden", "screen-reader", "skip-to-content",
    "skip-link", "back-to-top", "site-header", "site-footer",
    "global-nav", "primary-nav", "main-nav", "nav-menu", "menu-toggle", "hamburger",
)


def _is_boilerplate(a: dict) -> bool:
    """Decide from an element's attributes whether it's page chrome/ads, not content."""
    if a.get("aria-hidden") == "true" or "hidden" in a:
        return True
    style = (a.get("style") or "").replace(" ", "").lower()
    if "display:none" in style or "visibility:hidden" in style:
        return True
    if (a.get("role") or "").strip().lower() in _BAD_ROLES:
        return True
    if any(k.startswith("data-ad") for k in a):
        return True
    ident = ((a.get("class") or "") + " " + (a.get("id") or "")).lower()
    if not ident.strip():
        return False
    if any(sub in ident for sub in _BAD_SUBSTRINGS):
        return True
    return bool(set(re.split(r"[\s_\-]+", ident)) & _BAD_TOKENS)


class _MarkdownConverter(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.tag_stack: list[str] = []
        self._skip_depths: list[int] = []
        self.list_stack: list[list] = []
        self.in_pre = False
        self.link_href: str | None = None
        self.link_text: list[str] | None = None
        self.table: list[list[tuple]] | None = None
        self.row: list[tuple] | None = None
        self.cell: list[str] | None = None
        self._cell_colspan = 1
        self._cell_rowspan = 1
        self.base_url = ""

    def _skipping(self) -> bool:
        return bool(self._skip_depths)

    def _is_skippable(self, tag: str, a: dict) -> bool:
        if tag in SKIP_TAGS or tag == "img":
            return True
        cls = a.get("class", "") or ""
        if tag == "sup" and "reference" in cls:
            return True
        if any(sc in cls.split() for sc in _WIKI_SKIP):
            return True
        return _is_boilerplate(a)

    def _emit(self, text: str):
        if self.cell is not None:
            self.cell.append(text)
        elif self.link_text is not None:
            self.link_text.append(text)
        else:
            self.out.append(text)

    def _resolve(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("/") and self.base_url:
            return self.base_url.rstrip("/") + href
        return href

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)

        if tag not in _VOID:
            self.tag_stack.append(tag)
            if self._is_skippable(tag, a):
                self._skip_depths.append(len(self.tag_stack))
        else:
            if self._skipping():
                return
            if tag == "br":
                self._emit("\n")
            return

        if self._skipping():
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._emit("\n\n" + "#" * int(tag[1]) + " ")
        elif tag == "p":
            self._emit("\n\n")
        elif tag in ("b", "strong"):
            self._emit("**")
        elif tag in ("i", "em"):
            self._emit("*")
        elif tag in ("ul", "ol"):
            self.list_stack.append([tag, 0])
        elif tag == "li":
            depth = max(0, len(self.list_stack) - 1)
            indent = "    " * depth
            if self.list_stack and self.list_stack[-1][0] == "ol":
                self.list_stack[-1][1] += 1
                marker = f"{self.list_stack[-1][1]}. "
            else:
                marker = "- "
            self._emit("\n" + indent + marker)
        elif tag == "blockquote":
            self._emit("\n\n> ")
        elif tag == "pre":
            self.in_pre = True
            self._emit("\n\n```\n")
        elif tag == "code" and not self.in_pre:
            self._emit("`")
        elif tag == "a":
            href = a.get("href", "")
            if href and not href.startswith("#"):
                self.link_href = self._resolve(href)
                self.link_text = []
        elif tag == "table":
            if self.table is None:
                self.table = []
        elif tag == "tr":
            if self.table is not None:
                self.row = []
        elif tag in ("td", "th"):
            if self.table is not None:
                self.cell = []
                self._cell_colspan = _int_attr(a.get("colspan"), 1)
                self._cell_rowspan = _int_attr(a.get("rowspan"), 1)

    def handle_startendtag(self, tag, attrs):
        if not self._skipping() and tag == "br":
            self._emit("\n")

    def handle_endtag(self, tag):
        depth = len(self.tag_stack)
        if self._skip_depths and self._skip_depths[-1] == depth:
            self._skip_depths.pop()
            if self.tag_stack:
                self.tag_stack.pop()
            return

        skipping = self._skipping()
        if self.tag_stack:
            self.tag_stack.pop()
        if skipping or tag in _VOID:
            return

        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._emit("\n\n")
        elif tag == "p":
            self._emit("\n\n")
        elif tag in ("b", "strong"):
            self._emit("**")
        elif tag in ("i", "em"):
            self._emit("*")
        elif tag in ("ul", "ol"):
            if self.list_stack:
                self.list_stack.pop()
            if not self.list_stack:
                self._emit("\n")
        elif tag == "blockquote":
            self._emit("\n")
        elif tag == "pre":
            self.in_pre = False
            self._emit("\n```\n\n")
        elif tag == "code" and not self.in_pre:
            self._emit("`")
        elif tag == "a":
            if self.link_text is not None:
                text = "".join(self.link_text).strip()
                href = self.link_href or ""
                self.link_href = None
                self.link_text = None
                if text:
                    self._emit(f"[{text}]({href})" if href else text)
        elif tag in ("td", "th"):
            if self.cell is not None and self.row is not None:
                self.row.append(("".join(self.cell).strip(), self._cell_colspan, self._cell_rowspan))
                self.cell = None
        elif tag == "tr":
            if self.row is not None and self.table is not None:
                if self.row:
                    self.table.append(self.row)
                self.row = None
        elif tag == "table":
            if self.table is not None:
                rendered = _render_table(self.table)
                self.table = None
                self._emit(rendered)

    def handle_data(self, data):
        if self._skipping():
            return
        if self.in_pre:
            self._emit(data)
        else:
            collapsed = re.sub(r"\s+", " ", data)
            if collapsed:
                self._emit(collapsed)

    def result(self) -> str:
        return _tidy("".join(self.out))


def _int_attr(value, default: int) -> int:
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return default


def _render_table(rows: list[list[tuple]]) -> str:
    """Render rows of (text, colspan, rowspan) cells as a GFM table.

    Expands spans onto an explicit grid: a rowspan repeats its value down the
    first column; a colspan keeps the value in its first column and blanks the
    rest, so columns stay aligned.
    """
    matrix: dict[tuple[int, int], str] = {}
    occupied: set[tuple[int, int]] = set()
    nrows = len(rows)
    maxc = 0
    for r, raw in enumerate(rows):
        c = 0
        for text, colspan, rowspan in raw:
            while (r, c) in occupied:
                c += 1
            for dr in range(rowspan):
                for dc in range(colspan):
                    occupied.add((r + dr, c + dc))
                    matrix[(r + dr, c + dc)] = text if dc == 0 else ""
            c += colspan
        maxc = max(maxc, c)
    for (_r, cc) in occupied:
        maxc = max(maxc, cc + 1)
    if nrows == 0 or maxc == 0:
        return ""

    def clean(s: str) -> str:
        return re.sub(r"\s+", " ", s).replace("|", r"\|").strip()

    grid = [[clean(matrix.get((r, c), "")) for c in range(maxc)] for r in range(nrows)]
    grid = [row for row in grid if any(row)]
    if not grid:
        return ""
    header, body = grid[0], grid[1:]
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * maxc) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")
    return "\n\n" + "\n".join(lines) + "\n\n"


def _tidy(text: str) -> str:
    lines = [ln.rstrip() for ln in text.split("\n")]
    lines = [ln.lstrip(" ") if not ln.startswith("    ") else ln for ln in lines]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Main-content isolation (article mode)
# ---------------------------------------------------------------------------

# Priority order: semantic <main>, role=main, <article>, then well-known ids.
_MAIN_PATTERNS = (
    r"<main\b",
    r"<[a-zA-Z][\w-]*\b[^>]*\brole\s*=\s*['\"]?main(?=['\"\s>])",
    r"<article\b",
    r"<[a-zA-Z][\w-]*\b[^>]*\bid\s*=\s*['\"]?"
    r"(?:main-content|maincontent|main|content|article|post|story)(?=['\"\s>])",
)


def _slice_element(html: str, start: int) -> str | None:
    """Return the outer HTML of the element whose start tag begins at `start`,
    by depth-counting open/close tags of the same name."""
    tm = re.match(r"<([a-zA-Z][\w-]*)", html[start:start + 40])
    if not tm:
        return None
    tag = tm.group(1)
    depth = 0
    for m in re.finditer(rf"<(/?){re.escape(tag)}\b[^>]*?(/?)>", html[start:], re.I):
        if m.group(1) == "/":
            depth -= 1
            if depth <= 0:
                return html[start:start + m.end()]
        elif m.group(2) != "/":
            depth += 1
    return html[start:]  # unbalanced markup: take the rest


def _find_main_region(html: str) -> str | None:
    for pat in _MAIN_PATTERNS:
        m = re.search(pat, html, re.I)
        if not m:
            continue
        region = _slice_element(html, m.start())
        if region and len(region) >= 200:
            return region
    return None


def html_to_markdown(html: str, base_url: str = "") -> str:
    """Convert an HTML fragment or document to Markdown."""
    conv = _MarkdownConverter()
    conv.base_url = base_url
    conv.feed(html)
    return conv.result()


def page_to_markdown(html: str, url: str = "", mode: str = "article") -> dict:
    """Convert a full HTML page to Markdown.

    mode="article" isolates the main content region and strips chrome; mode="full"
    keeps the whole <body> (still dropping ads/nav/hidden boilerplate).
    """
    title_match = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
    title = unescape(re.sub(r"\s+", " ", title_match.group(1)).strip()) if title_match else ""

    body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.I | re.S)
    body = body_match.group(1) if body_match else html

    region = body
    if mode == "article":
        region = _find_main_region(body) or body

    base = re.match(r"(https?://[^/]+)", url)
    base_url = base.group(1) if base else ""

    body_md = html_to_markdown(region, base_url=base_url)
    header = f"# {title}\n\n" if title else ""
    if url:
        header += f"_Source: {url}_\n\n"
    return {"title": title, "url": url, "markdown": header + body_md}
