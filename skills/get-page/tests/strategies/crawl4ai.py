#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#   "crawl4ai",
# ]
# ///
"""Strategy: crawl4ai (real browser rendering + anti-detection).

Renders the page with a headless Chromium via Playwright (executing JS) and
extracts the main content as markdown. Tests whether browser rendering can
reach JS-only content that plain HTTP fetching cannot.
"""
import asyncio
import sys
from pathlib import Path

# This file is named crawl4ai.py, which would shadow the real `crawl4ai`
# package if its own directory sits on sys.path. Import _common with the dir
# temporarily on the path, then ensure that dir is NOT on sys.path so that
# `import crawl4ai` later resolves to the installed package, not this file.
_HERE = str(Path(__file__).parent)
sys.path.insert(0, _HERE)
from _common import emit, classify  # noqa: E402
while _HERE in sys.path:
    sys.path.remove(_HERE)

PAGE_TIMEOUT_MS = 45_000  # bounded so a single URL stays under ~60s


def extract_markdown(result) -> str:
    """crawl4ai's markdown may be a str or a MarkdownGenerationResult object."""
    md = getattr(result, "markdown", None)
    if md is None:
        return ""
    fit = getattr(md, "fit_markdown", None)
    if fit:
        return fit
    raw = getattr(md, "raw_markdown", None)
    if raw:
        return raw
    return str(md)


async def run(url: str):
    from crawl4ai import AsyncWebCrawler
    try:
        from crawl4ai import CrawlerRunConfig
        cfg = CrawlerRunConfig(page_timeout=PAGE_TIMEOUT_MS)
    except Exception:
        cfg = None
    async with AsyncWebCrawler() as crawler:
        if cfg is not None:
            return await crawler.arun(url=url, config=cfg)
        return await crawler.arun(url=url, page_timeout=PAGE_TIMEOUT_MS)


def main() -> None:
    if "--no-browser" in sys.argv:
        emit("skipped", trail="crawl4ai needs a browser")
        return

    url = sys.argv[1]
    try:
        result = asyncio.run(asyncio.wait_for(run(url), timeout=55))
    except asyncio.TimeoutError:
        emit("error", trail="crawl4ai render", error="timeout after 55s")
        return
    except Exception as e:
        msg = str(e)
        low = msg.lower()
        if "executable doesn't exist" in low or "playwright install" in low \
                or "browsertype.launch" in low or "no such file" in low:
            hint = ("chromium browser not found; run `crawl4ai-setup` or "
                    "`playwright install chromium`")
            emit("error", trail="crawl4ai render", error=hint)
            return
        emit("error", trail="crawl4ai render", error=msg[:300])
        return

    try:
        text = extract_markdown(result)
        status = getattr(result, "status_code", None)
        raw_html = getattr(result, "html", "") or ""
        verdict = classify(status, raw_html)
        if verdict in ("antibot", "blocked", "rate_limited", "not_found"):
            emit(verdict, text=text, trail="crawl4ai render", resolved=False)
        elif len(text) > 50:
            emit("usable", text=text, trail="crawl4ai render", resolved=True)
        else:
            emit("empty", text=text, trail="crawl4ai render", resolved=False)
    except Exception as e:
        emit("error", trail="crawl4ai render", error=str(e)[:300])


try:
    main()
except Exception as e:  # never crash without emitting
    emit("error", trail="crawl4ai render", error=str(e)[:300])
