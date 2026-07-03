"""Tests for HTML -> Markdown conversion, ad/boilerplate stripping, and article isolation."""

from netlens_mcp import convert

PAGE = """
<html><head><title>  Best BG3 Class  </title></head>
<body>
  <header class="site-header"><nav class="primary-nav"><a href="/">Home</a></nav></header>
  <div class="cookie-consent">We use cookies! <button>Accept</button></div>
  <aside class="sidebar"><div class="ad-slot">BUY GOLD NOW</div></aside>
  <div class="adsbygoogle">Sponsored: cheap potions</div>
  <div data-ad-slot="123">tracker</div>
  <div aria-hidden="true">offscreen aria junk</div>
  <p style="display:none">hidden tracking pixel</p>
  <main>
    <h1>Best Starting Class</h1>
    <p>The <strong>best</strong> class is the <em>Fighter</em>. See <a href="/wiki/fighter">details</a>.</p>
    <ul><li>High HP</li><li>Simple</li></ul>
    <div class="social-share">Share this!</div>
    <div class="related-articles"><a href="/x">Read more junk</a></div>
    <pre><code>roll(1, 20)</code></pre>
  </main>
  <footer class="site-footer">Copyright 2026</footer>
  <div class="newsletter-signup">Subscribe!</div>
</body></html>
"""


def test_title_and_source_header():
    out = convert.page_to_markdown(PAGE, "https://example.com/bg3")["markdown"]
    assert out.startswith("# Best BG3 Class")
    assert "_Source: https://example.com/bg3_" in out


def test_article_mode_keeps_real_content():
    out = convert.page_to_markdown(PAGE, "https://example.com", mode="article")["markdown"]
    for kept in ("Best Starting Class", "**best**", "*Fighter*", "High HP", "roll(1, 20)"):
        assert kept in out


def test_article_mode_strips_all_boilerplate():
    out = convert.page_to_markdown(PAGE, "https://example.com", mode="article")["markdown"].lower()
    for junk in (
        "cookie", "buy gold", "sponsored", "tracker", "aria junk", "hidden tracking",
        "share this", "read more junk", "copyright", "subscribe", "home",
    ):
        assert junk not in out, f"boilerplate leaked: {junk}"


def test_relative_links_resolved_to_absolute():
    out = convert.page_to_markdown(PAGE, "https://example.com/bg3", mode="article")["markdown"]
    assert "(https://example.com/wiki/fighter)" in out


def test_full_mode_keeps_body_but_still_strips_ads():
    # main region must be substantive (>200 HTML chars) for isolation to engage,
    # which is the realistic case; a near-empty <main> intentionally falls back.
    main_body = "Main content sentence. " * 15
    outside = "Sidebar filler outside main. " * 8
    html = f"""<html><body>
      <div class="adsbygoogle">AD JUNK</div>
      <div id="secondary"><p>{outside}</p></div>
      <main><p>{main_body}</p></main>
    </body></html>"""
    full = convert.page_to_markdown(html, mode="full")["markdown"]
    article = convert.page_to_markdown(html, mode="article")["markdown"]
    assert "Sidebar filler outside main." in full        # full keeps out-of-main content
    assert "Sidebar filler outside main." not in article  # article isolates <main>
    assert "Main content sentence." in full and "Main content sentence." in article
    assert "AD JUNK" not in full and "AD JUNK" not in article  # ads stripped in both


def test_article_isolation_prefers_semantic_article():
    story = "Real story body here. " * 15  # >200 chars so isolation engages
    html = f"""<html><body>
      <div><p>Plain sidebar paragraph that isolation should exclude.</p></div>
      <article><h2>Story</h2><p>{story}</p></article>
    </body></html>"""
    out = convert.page_to_markdown(html, mode="article")["markdown"]
    assert "Real story body here." in out
    assert "Plain sidebar paragraph" not in out  # isolated to <article>


def test_table_colspan_rowspan_alignment():
    html = """<table>
      <tr><th>Class</th><th>Tier</th></tr>
      <tr><td>Fighter</td><td>A</td></tr>
      <tr><td colspan="2">spans two</td></tr>
    </table>"""
    md = convert.html_to_markdown(html)
    assert "| Class | Tier |" in md
    assert "| --- | --- |" in md
    assert "| Fighter | A |" in md
    assert "| spans two |  |" in md  # colspan blanks the trailing cell


def test_reddit_style_form_content_preserved():
    # forms must NOT be skipped (Reddit wraps comment bodies in a form).
    html = "<html><body><form><div class='comment'><p>actual comment text</p></div></form></body></html>"
    out = convert.page_to_markdown(html, mode="full")["markdown"]
    assert "actual comment text" in out


def test_scripts_and_styles_dropped():
    html = "<html><body><main><script>evil()</script><style>.x{}</style><p>keep me</p></main></body></html>"
    out = convert.page_to_markdown(html, mode="article")["markdown"]
    assert "keep me" in out
    assert "evil()" not in out and ".x{}" not in out
