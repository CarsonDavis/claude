#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# ///
"""Strategy: the current get-page CLI (baseline)."""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _common import emit  # noqa: E402

LAUNCHER = str(Path(__file__).resolve().parents[2] / "get-page")


def main() -> None:
    url = sys.argv[1]
    cmd = [LAUNCHER, "auto", url, "--format", "json"]
    if "--no-browser" in sys.argv:
        cmd.append("--no-browser")
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=140)
    except subprocess.TimeoutExpired:
        emit("TIMEOUT", error="get-page subprocess timeout")
        return
    try:
        d = json.loads(p.stdout)
        emit(d.get("verdict", "?"),
             text=d.get("markdown") or d.get("text") or "",
             trail=d.get("trail", ""),
             resolved=d.get("resolved", d.get("verdict") == "pdf"))
    except json.JSONDecodeError:
        emit("failed", text=p.stdout, resolved=False, error=(p.stderr or "")[:200])


main()
