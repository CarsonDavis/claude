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


@dataclass
class Result:
    """Outcome of a single fetch attempt."""

    url: str
    rung: str
    final_url: str = ""
    status: int | None = None
    html: str = ""
    ok: bool = False
    error: str = ""
    notes: list[str] = field(default_factory=list)


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
        r.html = resp.text
        r.ok = resp.status_code < 400
    except Exception as exc:  # noqa: BLE001
        r.error = f"{type(exc).__name__}: {exc}"
    return r


# ----------------------------------------------------------------------------
# Rung 3 — headless browser (Playwright), lazy + break-glass
# ----------------------------------------------------------------------------

def fetch_browser(
    url: str, timeout: float = DEFAULT_TIMEOUT, scroll: bool = True
) -> Result:
    """Render the page in headless Chromium for genuinely JS-rendered content.

    Playwright is NOT a core dependency. If it is missing we re-exec ourselves
    through `uv run --with playwright ...` so the heavy dep is only ever pulled
    in when actually needed.
    """
    r = Result(url=url, rung="browser")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        # Re-exec once with playwright added to the ephemeral uv environment.
        if os.environ.get("GET_PAGE_BROWSER_REEXEC") != "1":
            env = dict(os.environ, GET_PAGE_BROWSER_REEXEC="1")
            os.execvpe(
                "uv",
                [
                    "uv", "run",
                    "--with", "playwright",
                    "--with", "playwright-stealth",
                    "--script", os.path.abspath(__file__),
                    *sys.argv[1:],
                ],
                env,
            )
        r.error = (
            "Playwright not available. Install once with:\n"
            "  uv tool run --with playwright playwright install chromium\n"
            "or run this script via `uv run --with playwright ...`."
        )
        return r

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            ctx = browser.new_context(
                user_agent=BROWSER_HEADERS["User-Agent"],
                locale="en-US",
            )
            try:
                from playwright_stealth import stealth_sync  # type: ignore

                page = ctx.new_page()
                stealth_sync(page)
            except Exception:  # noqa: BLE001 — stealth is best-effort
                page = ctx.new_page()

            page.goto(url, timeout=timeout * 1000, wait_until="domcontentloaded")
            if scroll:
                _scroll_to_load(page)
            r.html = page.content()
            r.final_url = page.url
            r.status = 200
            r.ok = True
            browser.close()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc)
        if "Executable doesn't exist" in msg or "playwright install" in msg:
            r.error = (
                "Chromium browser binary not installed (one-time setup). Run:\n"
                "  uv tool run --with playwright playwright install chromium"
            )
        else:
            r.error = f"{type(exc).__name__}: {exc}"
    return r


def _scroll_to_load(page, rounds: int = 10, pause: float = 0.4) -> None:
    """Scroll to the bottom repeatedly to trigger lazy-loaded content."""
    last_height = 0
    for _ in range(rounds):
        height = page.evaluate("document.body.scrollHeight")
        if height == last_height:
            break
        last_height = height
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(int(pause * 1000))


# ----------------------------------------------------------------------------
# Rung 1 — diagnose
# ----------------------------------------------------------------------------

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

    if antibot_hit:
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

def extract_readable(html: str, url: str = "") -> str:
    """Main-article HTML → clean Markdown (readability + markdownify)."""
    from readability import Document
    from markdownify import markdownify as md

    doc = Document(html)
    title = doc.short_title()
    summary_html = doc.summary(html_partial=True)
    body = md(summary_html, heading_style="ATX", strip=["a"] if False else None)
    body = "\n".join(line.rstrip() for line in body.splitlines())
    # Collapse runs of blank lines.
    out, blanks = [], 0
    for line in body.splitlines():
        if line.strip():
            blanks = 0
            out.append(line)
        else:
            blanks += 1
            if blanks <= 1:
                out.append(line)
    md_body = "\n".join(out).strip()
    header = f"# {title}\n\n" if title else ""
    return f"{header}{md_body}\n"


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


def auto(url: str, fmt: str = "md", allow_browser: bool = True) -> tuple[str, Result, dict]:
    """Walk the escalation ladder until usable content, then extract.

    Returns (output_string, winning_result, diagnosis).
    """
    trail: list[str] = []

    # Rung 0
    r = _retry_smart(url)
    d = diagnose(r)
    trail.append(f"smart → {d['verdict']}")

    # Rung 2 — for blocks / fingerprint / anti-bot / transport errors
    if d["verdict"] in ("blocked", "antibot", "error"):
        r2 = fetch_impersonate(url)
        d2 = diagnose(r2)
        trail.append(f"impersonate → {d2['verdict']}")
        if d2["verdict"] == "usable" or (not r.ok and r2.ok):
            r, d = r2, d2

    # Rung 3 — for client-rendered / still-challenged pages
    if allow_browser and d["verdict"] in ("js_shell", "empty", "antibot", "blocked"):
        r3 = fetch_browser(url)
        if r3.ok and r3.html:
            d3 = diagnose(r3)
            trail.append(f"browser → {d3['verdict']}")
            r, d = r3, d3
        else:
            trail.append(f"browser → failed ({r3.error.splitlines()[0] if r3.error else 'no content'})")
            r.notes.append(r3.error)

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
                "markdown": extract_readable(r.html, r.url),
                "jsonld": extract_jsonld(r.html),
            },
            indent=2,
            ensure_ascii=False,
        )
    else:  # md (default)
        provenance = f"<!-- get-page: {r.final_url or r.url} | {d['trail']} -->\n\n"
        out = provenance + extract_readable(r.html, r.url)
    return out, r, d


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def _read_html_arg(src: str) -> tuple[str, str]:
    """Resolve a url-or-'-' argument to (html, url). '-' reads stdin."""
    if src == "-":
        return sys.stdin.read(), ""
    if src.startswith("http://") or src.startswith("https://"):
        r = fetch_smart(src)
        # Escalate to TLS impersonation if the smart fetch was blocked or empty
        # (e.g. a 403 served with a short bot-policy body).
        if not r.ok or not r.html or (diagnose(r)["verdict"] in ("blocked", "antibot")):
            r2 = fetch_impersonate(src)
            if r2.ok and r2.html:
                r = r2
        return r.html, r.final_url or src
    # Treat as a local file path.
    with open(src, "r", encoding="utf-8") as fh:
        return fh.read(), src


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

    p_fetch = sub.add_parser("fetch", help="single fetch at a chosen rung")
    p_fetch.add_argument("url")
    p_fetch.add_argument(
        "--rung", choices=["smart", "impersonate", "browser"], default="smart"
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
        out, r, d = auto(args.url, fmt=args.format, allow_browser=not args.no_browser)
        print(out)
        return 0 if r.html else 2

    if args.cmd == "fetch":
        fn = {"smart": fetch_smart, "impersonate": fetch_impersonate, "browser": fetch_browser}[args.rung]
        r = fn(args.url)
        print(f"# rung={r.rung} status={r.status} final_url={r.final_url}", file=sys.stderr)
        if r.error:
            print(r.error, file=sys.stderr)
        print(r.html)
        return 0 if r.html else 2

    if args.cmd == "diagnose":
        r = fetch_smart(args.url)
        d = diagnose(r)
        print(json.dumps(d, indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "readable":
        html, url = _read_html_arg(args.src)
        print(extract_readable(html, url))
        return 0

    if args.cmd == "jsonld":
        html, _ = _read_html_arg(args.src)
        print(json.dumps(extract_jsonld(html), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "select":
        html, _ = _read_html_arg(args.src)
        print(json.dumps(extract_select(html, args.css), indent=2, ensure_ascii=False))
        return 0

    if args.cmd == "meta":
        html, url = _read_html_arg(args.src)
        print(json.dumps(extract_meta(html, url), indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
