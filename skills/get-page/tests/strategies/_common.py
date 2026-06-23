"""Shared contract + helpers for benchmark strategies.

A *strategy* is a self-contained `uv run --script` Python file in this directory
that takes a single URL argument and prints ONE JSON object to stdout:

    {"verdict": str, "trail": str, "text": str, "resolved": bool, "error": str}

  verdict   best-effort: usable | empty | blocked | antibot | rate_limited |
            not_found | pdf | error
  text      extracted main content (markdown / plain text)
  trail     short human note of what the strategy did
  resolved  True if real content was obtained
  error     "" or a short message

A strategy MUST always emit exactly one JSON line and never crash without one,
so the benchmark can compare every approach on the identical case set.

This module is imported by strategies for consistent block/PDF classification,
so the comparison is apples-to-apples. It has no third-party dependencies.
"""
from __future__ import annotations

import json

# Anti-bot / challenge signatures (kept in sync with get_page.py's detector).
BLOCK_SIGNATURES = (
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
    "access to this page has been denied",
    "you are using automation tools",
    "access denied",
    "pardon our interruption",
    "request unsuccessful. incapsula",
)


def classify(status: int | None, raw_html: str) -> str:
    """Best-effort verdict from HTTP status + raw HTML (pre-extraction)."""
    low = (raw_html or "").lower()
    if status == 429:
        return "rate_limited"
    if status in (401, 403):
        return "blocked"
    if status == 404:
        return "not_found"
    if status and status >= 500:
        return "blocked"
    if any(s in low for s in BLOCK_SIGNATURES):
        return "antibot"
    return "usable"


def emit(verdict: str, text: str = "", trail: str = "",
         resolved: bool | None = None, error: str = "") -> None:
    """Print the single normalized JSON result line and nothing else."""
    if resolved is None:
        resolved = verdict in ("usable", "pdf")
    print(json.dumps({
        "verdict": verdict,
        "trail": trail,
        "text": text or "",
        "resolved": bool(resolved),
        "error": error,
    }))
