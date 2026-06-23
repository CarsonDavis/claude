#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#     "httpx",
#     "brotli",
#     "curl_cffi",
#     "beautifulsoup4",
#     "lxml",
#     "readability-lxml",
#     "markdownify",
#     "pypdf",
# ]
# ///
"""get-page — tiered escalation toolkit for fetching stubborn web pages.

When a normal fetch (WebFetch / bare curl / requests) fails — 403, 429, an empty
JS-rendered shell, an anti-bot challenge, or garbled content — this walks an
escalation ladder until it gets usable content, then extracts it cleanly.

Rungs:
  0. smart fetch     httpx + realistic browser headers          (instant)
  1. diagnose        classify why a fetch failed / what's needed (instant)
  2. impersonate     curl_cffi TLS fingerprint spoof            (light)
  3. browser         Playwright + stealth, lazy-loaded          (break-glass)

Extractors (run on HTML from any rung): readable, jsonld, select, meta.

Run `get-page --help` or `get-page <command> --help` for usage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field

# ----------------------------------------------------------------------------
# Shared config
# ----------------------------------------------------------------------------

# A realistic, current desktop-Chrome header set. The single most common fix:
# many sites block the default httpx/requests User-Agent but serve a real one.
BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

DEFAULT_TIMEOUT = 30.0

# An HTTP result that parses as "usable" but yields less visible text than this,
# while carrying <script> markers, is treated as a likely client-rendered shell
# and gets a browser second opinion. Real articles clear this easily.
THIN_USABLE_CHARS = 700

# A deeper (browser) rung's render is only ADOPTED as the answer if it produced
# at least this much visible text. Below it, a "usable" verdict is untrustworthy
# (a thin challenge/partial page that merely lacks a block signature), so we keep
# the prior verdict instead of passing the thin page off as real content.
# Chosen to sit between the thin block pages observed (~500-800c) and a genuine
# minimal rendered page (quotes.toscrape.com/js ≈ 1600c).
SUBSTANTIAL_CHARS = 1000


@dataclass
class Result:
    """Outcome of a single fetch attempt."""

    url: str
    rung: str
    final_url: str = ""
    status: int | None = None
    html: str = ""
    content: bytes = b""
    content_type: str = ""
    ok: bool = False
    error: str = ""
    notes: list[str] = field(default_factory=list)


def is_pdf(r: Result) -> bool:
    """True if a fetch result is a PDF (by content-type or %PDF magic bytes)."""
    if "application/pdf" in (r.content_type or "").lower():
        return True
    return r.content[:5] == b"%PDF-"


# ----------------------------------------------------------------------------
# Rung 0 — smart HTTP fetch
# ----------------------------------------------------------------------------

def fetch_smart(url: str, timeout: float = DEFAULT_TIMEOUT) -> Result:
    """Plain HTTP with real browser headers, redirects, and decompression.

    Fixes the most common failure: a site that rejects the default library
    User-Agent but serves content to a real browser UA.
    """
    import httpx

    r = Result(url=url, rung="smart")
    try:
        with httpx.Client(
            headers=BROWSER_HEADERS,
            follow_redirects=True,
            timeout=timeout,
        ) as client:
            resp = client.get(url)
        r.status = resp.status_code
        r.final_url = str(resp.url)
        r.content = resp.content
        r.content_type = resp.headers.get("content-type", "")
        # Only decode to text for non-binary bodies; PDFs etc. stay as bytes so
        # we never feed NULL-byte binary into the HTML parsers.
        if not is_pdf(r):
            r.html = resp.text
        r.ok = resp.status_code < 400
    except Exception as exc:  # noqa: BLE001 — report, don't crash the ladder
        r.error = f"{type(exc).__name__}: {exc}"
    return r


# ----------------------------------------------------------------------------
# Rung 2 — TLS impersonation (curl_cffi)
# ----------------------------------------------------------------------------

def fetch_impersonate(
    url: str, timeout: float = DEFAULT_TIMEOUT, browser: str = "chrome"
) -> Result:
    """Fetch while impersonating a real browser's TLS/JA3 fingerprint.

    Defeats anti-bot systems that block on TLS fingerprint rather than headers,
    without needing a real browser.
    """
    from curl_cffi import requests as cffi

    r = Result(url=url, rung="impersonate")
    try:
        resp = cffi.get(
            url,
            headers={"Accept-Language": BROWSER_HEADERS["Accept-Language"]},
            impersonate=browser,
            timeout=timeout,
            allow_redirects=True,
        )
        r.status = resp.status_code
        r.final_url = resp.url
        r.content = resp.content
        r.content_type = resp.headers.get("content-type", "")
        if not is_pdf(r):
            r.html = resp.text
        r.ok = resp.status_code < 400
    except Exception as exc:  # noqa: BLE001
        r.error = f"{type(exc).__name__}: {exc}"
    return r


# ----------------------------------------------------------------------------
# Rung 3 — headless browser (crawl4ai), lazy + break-glass
# ----------------------------------------------------------------------------

def fetch_browser(
    url: str, timeout: float = DEFAULT_TIMEOUT, scroll: bool = True
) -> Result:
    """Render the page in a stealth headless browser via crawl4ai.

    crawl4ai (patchright-based, undetected) handles JS rendering and evades a
    broader set of anti-bot defenses than bare Playwright — in benchmarking it
    was the only rung that recovered client-rendered listing grids and survived
    hosts that crash plain Chromium with ERR_HTTP2_PROTOCOL_ERROR.

    It is NOT a core dependency (it pulls ~90 packages). If missing we re-exec
    once through `uv run --with crawl4ai ...` so it is only ever installed when
    the browser rung is actually reached.

    We keep the rendered *HTML* (not crawl4ai's markdown) so get-page's own
    diagnose/extraction layer still runs on top — that layer is what flags a
    rendered block/challenge page that crawl4ai alone would call "usable".
    """
    r = Result(url=url, rung="browser")

    try:
        import crawl4ai  # noqa: F401
    except ImportError:
        _reexec_with_browser_deps()
        r.error = (
            "crawl4ai not available. Install once with:\n"
            "  uv run --with crawl4ai --with nodriver --script <this script> ..."
        )
        return r

    try:
        html, final_url, status = _crawl4ai_render(url, timeout, scroll)
        r.html = html or ""
        r.final_url = final_url or url
        r.status = status or (200 if html else None)
        r.ok = bool(html)
        if not html:
            r.error = "browser returned no content"
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if any(k in msg.lower() for k in ("executable", "browser", "playwright", "chromium")):
            r.error = (
                "Browser binary missing (one-time setup). Run:\n"
                "  uv tool run --with playwright playwright install chromium"
            )
        else:
            r.error = f"{type(exc).__name__}: {exc}"
    return r


def _crawl4ai_render(url: str, timeout: float, scroll: bool):
    """Render via crawl4ai; return (rendered_html, final_url, status_code)."""
    import asyncio

    from crawl4ai import AsyncWebCrawler

    async def run():
        async with AsyncWebCrawler() as crawler:
            try:
                result = await crawler.arun(
                    url=url, page_timeout=int(timeout * 1000), scan_full_page=scroll
                )
            except TypeError:
                # Older/newer signatures may not accept those kwargs.
                result = await crawler.arun(url=url)
            return result

    result = asyncio.run(asyncio.wait_for(run(), timeout=timeout + 30))
    html = getattr(result, "html", "") or getattr(result, "cleaned_html", "") or ""
    final_url = getattr(result, "url", url) or url
    status = getattr(result, "status_code", None)
    return html, final_url, status


def _reexec_with_browser_deps() -> None:
    """Re-exec once through uv with both browser engines available.

    The browser rungs (crawl4ai, nodriver) are not core deps. The first time one
    is reached we re-exec the script with both added to the ephemeral uv env, so
    a single install covers either engine the ladder may need.
    """
    if os.environ.get("GET_PAGE_BROWSER_REEXEC") == "1":
        return
    env = dict(os.environ, GET_PAGE_BROWSER_REEXEC="1")
    os.execvpe(
        "uv",
        ["uv", "run", "--with", "crawl4ai", "--with", "nodriver",
         "--script", os.path.abspath(__file__), *sys.argv[1:]],
        env,
    )


# ----------------------------------------------------------------------------
# Rung 4 — undetected headful browser (nodriver), deepest break-glass
# ----------------------------------------------------------------------------

# macOS Google Chrome; nodriver auto-detects if this isn't present.
_CHROME_MAC = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def fetch_nodriver(url: str, timeout: float = DEFAULT_TIMEOUT) -> Result:
    """Render in real Google Chrome via nodriver — the deepest, last-resort rung.

    nodriver drives Chrome over raw CDP with no WebDriver flag. In head-to-head
    testing it defeated Cloudflare on hosts where Playwright AND patchright
    (crawl4ai's engine) were blocked even headful — it returned the real product
    page where they got a 342-char challenge.

    Runs HEADFUL by default (a visible Chrome window): that is what actually
    beats Cloudflare, and nodriver's own headless=True fails to connect on macOS.
    Set GET_PAGE_NODRIVER_HEADLESS=1 to force windowless (weaker, more detectable).
    """
    r = Result(url=url, rung="nodriver")
    try:
        import nodriver  # noqa: F401
    except ImportError:
        _reexec_with_browser_deps()
        r.error = "nodriver not available (re-exec with --with nodriver failed)"
        return r
    try:
        html, final_url = _nodriver_render(url, timeout)
        r.html = html or ""
        r.final_url = final_url or url
        r.status = 200 if html else None
        r.ok = bool(html)
        if not html:
            r.error = "nodriver returned no content"
    except Exception as exc:  # noqa: BLE001
        r.error = f"{type(exc).__name__}: {exc}"
    return r


def _nodriver_render(url: str, timeout: float):
    """Render via nodriver (headful real Chrome); return (html, final_url)."""
    import asyncio
    import os.path

    import nodriver as uc

    chrome = _CHROME_MAC if os.path.exists(_CHROME_MAC) else None
    headless = os.environ.get("GET_PAGE_NODRIVER_HEADLESS") == "1"
    browser_args = ["--headless=new"] if headless else []

    async def run():
        browser = await uc.start(
            headless=False, no_sandbox=True,
            browser_executable_path=chrome, browser_args=browser_args,
        )
        try:
            page = await browser.get(url)
            await page.sleep(6)  # let the JS challenge clear
            html = await page.get_content()
            try:
                final_url = await page.evaluate("location.href")
            except Exception:  # noqa: BLE001
                final_url = url
            return html or "", (final_url if isinstance(final_url, str) else url)
        finally:
            try:
                res = browser.stop()
                if asyncio.iscoroutine(res):
                    await res
            except Exception:  # noqa: BLE001
                pass

    return uc.loop().run_until_complete(
        asyncio.wait_for(run(), timeout=timeout + 25)
    )


# ----------------------------------------------------------------------------
# Rung 1 — diagnose
# ----------------------------------------------------------------------------

# A page is only treated as an anti-bot block if a signature matches AND its
# visible text is under this many chars. Real pages can carry stray challenge
# strings; genuine challenge/denial pages are short.
_ANTIBOT_MAX_TEXT = 2500

# Signatures for interactive anti-bot / challenge pages.
_ANTIBOT_SIGNATURES = (
    "just a moment...",
    "cf-browser-verification",
    "cf_chl",
    "_cf_chl_opt",
    "attention required! | cloudflare",
    "checking if the site connection is secure",
    "enable javascript and cookies to continue",
    "px-captcha",
    "perimeterx",
    "/_incapsula_",
    "are you a human",
    # PerimeterX / HUMAN "Access Denied" template (e.g. Mouser, Newark).
    "access to this page has been denied",
    "you are using automation tools",
    "access denied",
    "pardon our interruption",  # Distil/Imperva
    "request unsuccessful. incapsula",
)

# Containers that signal a client-rendered SPA shell with no server HTML.
_SPA_ROOTS = ('id="root"', 'id="__next"', 'id="app"', 'data-reactroot')


def _visible_text_len(html: str) -> int:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    body = soup.body or soup
    return len(body.get_text(" ", strip=True))


def diagnose(result: Result) -> dict:
    """Classify a fetch result so `auto` can route to the right next rung.

    Returns a dict with: verdict, reason, recommend (next rung), and signals.
    """
    html = result.html or ""
    low = html.lower()
    status = result.status
    text_len = _visible_text_len(html) if html else 0
    has_spa_root = any(sig in low for sig in _SPA_ROOTS)
    antibot_hit = next((s for s in _ANTIBOT_SIGNATURES if s in low), None)

    d = {
        "url": result.url,
        "rung": result.rung,
        "status": status,
        "text_len": text_len,
        "verdict": "usable",
        "reason": "",
        "recommend": None,
        "signals": {
            "spa_root": has_spa_root,
            "antibot": antibot_hit,
            "error": result.error or None,
        },
    }

    if result.error and not html:
        d["verdict"] = "error"
        d["reason"] = result.error
        d["recommend"] = "impersonate"
        return d

    if status == 429:
        d["verdict"] = "rate_limited"
        d["reason"] = "HTTP 429 Too Many Requests"
        d["recommend"] = "retry"
        return d
    if status in (401, 403):
        d["verdict"] = "blocked"
        d["reason"] = f"HTTP {status} — likely bot/TLS fingerprint block"
        d["recommend"] = "impersonate"
        return d
    if status == 404:
        d["verdict"] = "not_found"
        d["reason"] = "HTTP 404"
        d["recommend"] = None
        return d
    if status and status >= 500:
        d["verdict"] = "server_error"
        d["reason"] = f"HTTP {status}"
        d["recommend"] = "retry"
        return d

    # Anti-bot challenge — but only when the page is also THIN. A fully rendered
    # page (e.g. a 23k-char product page) can legitimately contain a stray
    # Cloudflare "challenge-platform" script string; that is not a block. Real
    # challenge/denial pages are short.
    if antibot_hit and text_len < _ANTIBOT_MAX_TEXT:
        d["verdict"] = "antibot"
        d["reason"] = f"anti-bot challenge page (matched '{antibot_hit}')"
        # Impersonation sometimes clears it; otherwise a real browser.
        d["recommend"] = "impersonate" if result.rung == "smart" else "browser"
        return d

    # Thin visible text with any script presence suggests client-rendered
    # content (covers both classic SPA shells and server pages that inject
    # their body via JS, e.g. quotes.toscrape.com/js). >200 chars of real text
    # is treated as genuine content so normal short pages don't over-escalate.
    if text_len < 200 and (has_spa_root or "<script" in low):
        d["verdict"] = "js_shell"
        d["reason"] = (
            f"thin body ({text_len} chars visible text) with "
            f"{'SPA root' if has_spa_root else 'script'} markers "
            "— content is likely client-rendered"
        )
        d["recommend"] = "browser"
        return d

    if text_len < 50:
        d["verdict"] = "empty"
        d["reason"] = f"near-empty body ({text_len} chars)"
        d["recommend"] = "browser"
        return d

    d["reason"] = f"{text_len} chars of visible text"
    return d


# ----------------------------------------------------------------------------
# Extractors — operate on raw HTML from any rung
# ----------------------------------------------------------------------------

def _collapse_blanks(text: str) -> str:
    """Trim trailing whitespace and collapse runs of blank lines to one."""
    out, blanks = [], 0
    for line in text.splitlines():
        line = line.rstrip()
        if line:
            blanks = 0
            out.append(line)
        else:
            blanks += 1
            if blanks <= 1:
                out.append(line)
    return "\n".join(out).strip()


def _fallback_body_md(html: str) -> str:
    """Markdownify the whole body with chrome stripped, preserving links.

    readability is tuned for articles and discards link lists, which collapses
    search-result and listing pages to title-only. This denser conversion keeps
    the result anchors at the cost of some navigation noise.
    """
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md

    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "svg", "form"]):
        tag.decompose()
    target = soup.body or soup
    return _collapse_blanks(md(str(target), heading_style="ATX"))


def _link_count(md_text: str) -> int:
    return md_text.count("](")


def extract_readable(html: str, url: str = "") -> str:
    """Main-content HTML → clean Markdown.

    Uses readability for articles; falls back to a link-preserving full-body
    conversion when readability collapses the page to almost nothing (SERPs,
    JS listing grids), so result links aren't silently dropped.
    """
    from readability import Document

    from markdownify import markdownify as md

    doc = Document(html)
    title = doc.short_title()
    md_body = _collapse_blanks(md(doc.summary(html_partial=True), heading_style="ATX"))

    # Detect a collapsed extraction: little body text or no links retained, while
    # the raw page clearly has many anchors. Then prefer the denser fallback.
    raw_links = html.count("href=")
    if (len(md_body) < 200 or _link_count(md_body) == 0) and raw_links > 5:
        fb = _fallback_body_md(html)
        if _link_count(fb) > _link_count(md_body) or len(fb) > len(md_body):
            md_body = fb

    header = f"# {title}\n\n" if title else ""
    return f"{header}{md_body}\n"


def _main_content_len(html: str) -> int:
    """Visible-text length of the readability *main content* only (excludes nav/
    chrome). Small here despite a large raw page == likely a client-rendered
    shell whose real data isn't in the HTML."""
    try:
        from readability import Document
        return _visible_text_len(Document(html).summary(html_partial=True))
    except Exception:  # noqa: BLE001
        return _visible_text_len(html)


def extract_pdf(data: bytes) -> str:
    """Extract text from a PDF byte stream as Markdown-ish plain text."""
    import io

    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            parts.append(f"<!-- page {i} -->\n{text}")
    if not parts:
        return "(PDF contained no extractable text — likely scanned/image-only.)\n"
    return "\n\n".join(parts) + "\n"


def extract_jsonld(html: str) -> list:
    """Return all application/ld+json structured-data blocks, parsed."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    blocks = []
    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text()
        if not raw:
            continue
        try:
            blocks.append(json.loads(raw))
        except json.JSONDecodeError:
            # Some sites concatenate multiple objects or include trailing junk.
            try:
                blocks.append(json.loads(raw.strip().rstrip(";")))
            except json.JSONDecodeError:
                blocks.append({"_unparsed": raw.strip()[:500]})
    return blocks


def extract_select(html: str, css: str) -> list:
    """Return text + key attributes for every element matching a CSS selector."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    out = []
    for el in soup.select(css):
        item = {"text": el.get_text(" ", strip=True)}
        if el.get("href"):
            item["href"] = el["href"]
        if el.get("src"):
            item["src"] = el["src"]
        out.append(item)
    return out


def extract_meta(html: str, url: str = "") -> dict:
    """Page metadata: title, meta/OpenGraph tags, canonical, link inventory."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    meta: dict = {"url": url}
    if soup.title and soup.title.string:
        meta["title"] = soup.title.string.strip()

    tags: dict = {}
    for m in soup.find_all("meta"):
        key = m.get("property") or m.get("name")
        if key and m.get("content"):
            tags[key] = m["content"]
    meta["meta"] = tags

    canonical = soup.find("link", rel="canonical")
    if canonical and canonical.get("href"):
        meta["canonical"] = canonical["href"]

    links = []
    for a in soup.find_all("a", href=True):
        links.append({"text": a.get_text(" ", strip=True)[:80], "href": a["href"]})
    meta["link_count"] = len(links)
    meta["links"] = links[:50]
    return meta


# ----------------------------------------------------------------------------
# auto — walk the ladder
# ----------------------------------------------------------------------------

def _retry_smart(url: str, attempts: int = 3) -> Result:
    """Smart fetch honoring 429 with backoff + jitter (deterministic jitter)."""
    delay = 1.0
    r = fetch_smart(url)
    for i in range(attempts - 1):
        if r.status != 429:
            return r
        wait = delay * (2**i) + (i * 0.3)  # backoff + mild spread, no RNG
        r.notes.append(f"429 → waiting {wait:.1f}s before retry")
        time.sleep(min(wait, 10))
        r = fetch_smart(url)
    return r


def _pdf_output(r: Result, fmt: str, trail: str) -> str:
    """Render a PDF fetch result in the requested output format."""
    text = extract_pdf(r.content)
    if fmt == "json":
        return json.dumps(
            {
                "url": r.url,
                "final_url": r.final_url,
                "status": r.status,
                "rung": r.rung,
                "trail": trail,
                "verdict": "pdf",
                "content_type": "application/pdf",
                "text": text,
            },
            indent=2,
            ensure_ascii=False,
        )
    if fmt == "raw":
        return text
    return f"<!-- get-page: {r.final_url or r.url} | {trail} -->\n\n{text}"


def _should_adopt(prev_d: dict, prev_text: int, new_d: dict, new_text: int) -> bool:
    """Whether a deeper rung's render should replace the current best result.

    Adopt only when the render is genuinely usable with substantial content, or
    when it strictly beats an already-usable result. A thin "usable" page (e.g. a
    partial/challenge page that merely lacks a block signature) is NOT adopted —
    we keep the prior blocked/antibot verdict so it isn't passed off as content.
    """
    if new_d["verdict"] == "usable" and new_text >= SUBSTANTIAL_CHARS:
        return True
    if prev_d["verdict"] == "usable" and new_d["verdict"] == "usable" and new_text > prev_text:
        return True
    return False


def auto(url: str, fmt: str = "md", allow_browser: bool = True,
         allow_headful: bool = True) -> tuple[str, Result, dict]:
    """Walk the escalation ladder until usable content, then extract.

    Returns (output_string, winning_result, diagnosis).
    """
    trail: list[str] = []

    # Rung 0
    r = _retry_smart(url)
    if is_pdf(r):
        trail.append("smart → pdf")
        return _pdf_output(r, fmt, " | ".join(trail)), r, {"verdict": "pdf", "trail": " | ".join(trail)}
    d = diagnose(r)
    trail.append(f"smart → {d['verdict']}")

    # Rung 2 — for blocks / fingerprint / anti-bot / transport errors
    if d["verdict"] in ("blocked", "antibot", "error"):
        r2 = fetch_impersonate(url)
        if is_pdf(r2):
            trail.append("impersonate → pdf")
            return _pdf_output(r2, fmt, " | ".join(trail)), r2, {"verdict": "pdf", "trail": " | ".join(trail)}
        d2 = diagnose(r2)
        trail.append(f"impersonate → {d2['verdict']}")
        if d2["verdict"] == "usable" or (not r.ok and r2.ok):
            r, d = r2, d2

    # Rung 3 — render in a real browser for client-rendered / still-challenged
    # pages. Also take a browser "second opinion" when the HTTP result parsed as
    # usable but is suspiciously thin with script markers (false-usable JS grids
    # like octopart/findchips that serve a shell over plain HTTP).
    cur_text = _visible_text_len(r.html) if r.html else 0
    # Measure *main content* (chrome excluded): a page full of nav boilerplate
    # but with little real content, plus scripts, is a likely client-rendered
    # shell whose data needs a browser even though it parsed as "usable".
    cur_main = _main_content_len(r.html) if r.html else 0
    thin_usable = (
        d["verdict"] == "usable"
        and cur_main < THIN_USABLE_CHARS
        and "<script" in (r.html or "").lower()
    )
    if allow_browser and (
        d["verdict"] in ("js_shell", "empty", "antibot", "blocked") or thin_usable
    ):
        r3 = fetch_browser(url)
        if r3.ok and r3.html:
            d3 = diagnose(r3)
            new_text = _visible_text_len(r3.html)
            if _should_adopt(d, cur_text, d3, new_text):
                trail.append(f"browser → {d3['verdict']}")
                r, d = r3, d3
                cur_text = new_text
            else:
                trail.append(f"browser → {d3['verdict']} (thin {new_text}c, kept {d['verdict']})")
        else:
            trail.append(f"browser → failed ({r3.error.splitlines()[0] if r3.error else 'no content'})")
            r.notes.append(r3.error)

    # Rung 4 — deepest break-glass: undetected headful Chrome (nodriver). Only
    # when everything above still failed to reach usable content (e.g. Cloudflare
    # that crawl4ai/patchright can't pass). Pops a visible window; last resort.
    if allow_browser and allow_headful and d["verdict"] in ("antibot", "blocked", "empty", "js_shell"):
        r4 = fetch_nodriver(url)
        if r4.ok and r4.html:
            d4 = diagnose(r4)
            new_text = _visible_text_len(r4.html)
            if _should_adopt(d, _visible_text_len(r.html or ""), d4, new_text):
                trail.append(f"nodriver → {d4['verdict']}")
                r, d = r4, d4
            else:
                trail.append(f"nodriver → {d4['verdict']} (thin {new_text}c, kept {d['verdict']})")
        else:
            trail.append(f"nodriver → failed ({r4.error.splitlines()[0] if r4.error else 'no content'})")
            r.notes.append(r4.error)

    d["trail"] = " | ".join(trail)

    if not r.html:
        return (
            f"FAILED to retrieve usable content.\n"
            f"Ladder: {d['trail']}\n"
            f"Last verdict: {d['verdict']} — {d['reason']}\n"
            + (f"Notes: {'; '.join(n for n in r.notes if n)}\n" if any(r.notes) else ""),
            r,
            d,
        )

    # We have HTML but never reached a clean "usable" verdict — the body is
    # likely a block/challenge page. Surface that instead of passing it off as
    # real content (an agent must not trust a denial page as the answer).
    d["resolved"] = d["verdict"] == "usable"
    warning = ""
    if d["verdict"] != "usable":
        warning = (
            f"⚠ get-page did NOT reach usable content (verdict: {d['verdict']} — "
            f"{d['reason']}). The body below is probably a block/challenge page, "
            f"not the real content.\nLadder: {d['trail']}\n\n"
        )

    if fmt == "raw":
        out = r.html
    elif fmt == "json":
        out = json.dumps(
            {
                "url": r.url,
                "final_url": r.final_url,
                "status": r.status,
                "rung": r.rung,
                "trail": d["trail"],
                "verdict": d["verdict"],
                "resolved": d["resolved"],
                "markdown": extract_readable(r.html, r.url),
                "jsonld": extract_jsonld(r.html),
            },
            indent=2,
            ensure_ascii=False,
        )
    else:  # md (default)
        provenance = f"<!-- get-page: {r.final_url or r.url} | {d['trail']} -->\n\n"
        out = warning + provenance + extract_readable(r.html, r.url)
    return out, r, d


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def fetch_resolved(src: str) -> Result:
    """Resolve a url / file path / '-' (stdin) to a Result.

    URLs use the smart→impersonate HTTP escalation; PDFs are kept as bytes.
    """
    if src == "-":
        data = sys.stdin.buffer.read()
        r = Result(url="", rung="stdin", content=data, ok=True)
        if data[:5] == b"%PDF-":
            r.content_type = "application/pdf"
        else:
            r.html = data.decode("utf-8", "replace")
        return r

    if src.startswith("http://") or src.startswith("https://"):
        r = fetch_smart(src)
        # Escalate to TLS impersonation if blocked or empty (e.g. a 403 served
        # with a short bot-policy body). PDFs are already usable as bytes.
        if not is_pdf(r) and (
            not r.ok or not r.html or diagnose(r)["verdict"] in ("blocked", "antibot")
        ):
            r2 = fetch_impersonate(src)
            if r2.ok and (r2.html or is_pdf(r2)):
                r = r2
        if not r.final_url:
            r.final_url = src
        return r

    # Treat as a local file path (read as bytes to support PDFs).
    with open(src, "rb") as fh:
        data = fh.read()
    r = Result(url=src, rung="file", content=data, final_url=src, ok=True)
    if data[:5] == b"%PDF-":
        r.content_type = "application/pdf"
    else:
        r.html = data.decode("utf-8", "replace")
    return r


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="get-page",
        description="Tiered escalation toolkit for fetching stubborn web pages.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_auto = sub.add_parser("auto", help="walk the ladder, return clean content")
    p_auto.add_argument("url")
    p_auto.add_argument("--format", choices=["md", "json", "raw"], default="md")
    p_auto.add_argument("--no-browser", action="store_true", help="cap at HTTP-only rungs")
    p_auto.add_argument("--no-headful", action="store_true",
                        help="skip the deepest nodriver rung (no visible browser window)")

    p_fetch = sub.add_parser("fetch", help="single fetch at a chosen rung")
    p_fetch.add_argument("url")
    p_fetch.add_argument(
        "--rung", choices=["smart", "impersonate", "browser", "nodriver"], default="smart"
    )

    p_diag = sub.add_parser("diagnose", help="classify why a fetch fails / what's needed")
    p_diag.add_argument("url")

    p_read = sub.add_parser("readable", help="HTML/URL/stdin → clean markdown")
    p_read.add_argument("src", help="url, file path, or - for stdin")

    p_json = sub.add_parser("jsonld", help="extract application/ld+json blocks")
    p_json.add_argument("src", help="url, file path, or - for stdin")

    p_sel = sub.add_parser("select", help="return elements matching a CSS selector")
    p_sel.add_argument("src", help="url, file path, or - for stdin")
    p_sel.add_argument("css")

    p_meta = sub.add_parser("meta", help="title, meta/OG tags, canonical, links")
    p_meta.add_argument("src", help="url, file path, or - for stdin")

    args = parser.parse_args(argv)

    if args.cmd == "auto":
        out, r, d = auto(args.url, fmt=args.format, allow_browser=not args.no_browser,
                         allow_headful=not args.no_headful)
        print(out)
        if d.get("verdict") == "pdf" or d.get("resolved"):
            return 0
        return 2  # no content, or content that's a block/challenge page

    if args.cmd == "fetch":
        fn = {"smart": fetch_smart, "impersonate": fetch_impersonate,
              "browser": fetch_browser, "nodriver": fetch_nodriver}[args.rung]
        r = fn(args.url)
        print(f"# rung={r.rung} status={r.status} final_url={r.final_url}", file=sys.stderr)
        if r.error:
            print(r.error, file=sys.stderr)
        if is_pdf(r):
            print("# application/pdf — use `get-page readable` for extracted text", file=sys.stderr)
            print(extract_pdf(r.content))
            return 0
        print(r.html)
        return 0 if r.html else 2

    if args.cmd == "diagnose":
        r = fetch_smart(args.url)
        d = diagnose(r)
        print(json.dumps(d, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "readable":
        r = fetch_resolved(args.src)
        if is_pdf(r):
            print(extract_pdf(r.content))
        else:
            print(extract_readable(r.html, r.final_url or r.url))
        return 0

    if args.cmd == "jsonld":
        r = fetch_resolved(args.src)
        print(json.dumps(extract_jsonld(r.html), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "select":
        r = fetch_resolved(args.src)
        print(json.dumps(extract_select(r.html, args.css), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "meta":
        r = fetch_resolved(args.src)
        print(json.dumps(extract_meta(r.html, r.final_url or r.url), indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
