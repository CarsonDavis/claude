#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = [
#     "trafilatura",
#     "lxml_html_clean",
# ]
# ///
"""Strategy: trafilatura (open-source HTTP fetch + main-content extraction)."""
import sys
from pathlib import Path

_HERE = str(Path(__file__).parent)

# This file is named trafilatura.py and lives in the same directory Python puts
# on sys.path[0] when running a script. Drop that directory so `import
# trafilatura` resolves to the installed library, not this file itself.
sys.path[:] = [p for p in sys.path if p not in ("", _HERE, str(Path(_HERE).resolve()))]
import trafilatura  # noqa: E402

# Now restore the script directory so we can import the shared helpers.
sys.path.insert(0, _HERE)
from _common import emit, classify, BLOCK_SIGNATURES  # noqa: E402


def main() -> None:
    url = sys.argv[1]

    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        emit("error", trail="trafilatura fetch returned None",
             resolved=False, error="fetch_url returned None")
        return

    # No status code from fetch_url; rely on block-signature detection.
    verdict = classify(None, downloaded)
    if verdict == "antibot" or any(s in downloaded.lower() for s in BLOCK_SIGNATURES):
        emit("antibot", trail="trafilatura fetch (anti-bot signature)",
             resolved=False)
        return

    extracted = trafilatura.extract(
        downloaded,
        output_format="markdown",
        include_links=True,
        include_tables=True,
    )

    if not extracted:
        emit("empty", trail="trafilatura fetch+extract (no main content)",
             resolved=False)
        return

    emit("usable", text=extracted, trail="trafilatura fetch+extract",
         resolved=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        emit("error", error=str(e))
