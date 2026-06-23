#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["nodriver", "beautifulsoup4", "lxml"]
# ///
"""Strategy: nodriver — the async successor to undetected-chromedriver.

Drives real Google Chrome over CDP with no WebDriver flag, which benchmarks
suggest beats patchright/crawl4ai on Cloudflare. Renders the page, then extracts
visible text (same basis as the other strategies) for the benchmark.

Set GET_PAGE_HEADFUL=1 to run a visible Chrome window (more stealthy on some
anti-bot systems, but pops a window per URL).
"""
import asyncio
import os
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
sys.path.insert(0, str(_here))
from _common import emit, classify  # noqa: E402

# This file is named nodriver.py; drop its own dir from sys.path so
# `import nodriver` resolves to the installed package, not this script.
sys.path = [p for p in sys.path if Path(p).resolve() != _here]

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
HEADLESS = os.environ.get("GET_PAGE_HEADFUL") != "1"


def _visible_text(html: str) -> str:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()
    return soup.get_text(" ", strip=True)


async def _render(url: str, timeout: float):
    import nodriver as uc
    # nodriver's own headless=True fails to connect to Chrome on macOS; use
    # Chrome's --headless=new flag instead (windowless and it connects).
    browser_args = ["--headless=new"] if HEADLESS else []
    browser = await uc.start(
        headless=False, browser_executable_path=CHROME,
        no_sandbox=True, browser_args=browser_args,
    )
    try:
        page = await browser.get(url)
        await page.sleep(5)  # let JS / anti-bot challenge settle
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


def main() -> None:
    url = sys.argv[1]
    if "--no-browser" in sys.argv:
        emit("skipped", trail="nodriver needs a browser")
        return
    try:
        import nodriver as uc
        timeout = 45.0
        html, final_url = uc.loop().run_until_complete(
            asyncio.wait_for(_render(url, timeout), timeout=timeout + 20)
        )
        verdict = classify(None, html)
        text = _visible_text(html)
        if verdict == "usable" and len(text) < 50:
            verdict = "empty"
        emit(verdict, text=text, trail="nodriver render",
             resolved=verdict == "usable")
    except Exception as exc:  # noqa: BLE001
        emit("error", error=f"{type(exc).__name__}: {str(exc)[:300]}")


main()
