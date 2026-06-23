#!/usr/bin/env python3
"""Benchmark harness for get-page — compare approaches on one fixed case set.

Strategies are self-contained scripts in ./strategies/ (see strategies/_common.py
for the contract). Each is run via `uv run --script` so it carries its own deps
and approaches stay isolated — you can build several in parallel and compare them
on the identical real-world URLs in cases.py.

Usage:
  ./benchmark.py                                  # default 'getpage' strategy
  ./benchmark.py --strategy trafilatura
  ./benchmark.py --strategy all                   # run every discovered strategy
  ./benchmark.py --strategy all --category js_shell   # just the frontier
  ./benchmark.py --no-browser --case mouser
  ./benchmark.py --strategy all --json out.json
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cases import CASES  # noqa: E402

STRAT_DIR = HERE / "strategies"
CORE = {"baseline", "pdf", "hard_block", "not_found"}  # failure here = regression


def discover_strategies() -> dict[str, Path]:
    return {
        p.stem: p
        for p in sorted(STRAT_DIR.glob("*.py"))
        if not p.name.startswith("_")
    }


def run_strategy(script: Path, url: str, allow_browser: bool, timeout: int) -> dict:
    """Invoke a strategy script and normalize its single JSON line."""
    cmd = ["uv", "run", "--quiet", "--script", str(script), url]
    if not allow_browser:
        cmd.append("--no-browser")
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"verdict": "TIMEOUT", "trail": "", "text": "", "resolved": False,
                "elapsed": float(timeout), "error": "timeout"}
    elapsed = time.time() - t0
    line = next((ln for ln in reversed(p.stdout.splitlines()) if ln.strip().startswith("{")), "")
    try:
        d = json.loads(line)
        d["elapsed"] = elapsed
        d.setdefault("text", "")
        d.setdefault("verdict", "?")
        d.setdefault("trail", "")
        d.setdefault("resolved", False)
        d.setdefault("error", "")
        return d
    except json.JSONDecodeError:
        return {"verdict": "error", "trail": "", "text": "", "resolved": False,
                "elapsed": elapsed, "error": (p.stderr or "no JSON output")[:200]}


def evaluate(expect: dict, res: dict) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    text = res.get("text") or ""
    if "verdict_in" in expect and res["verdict"] not in expect["verdict_in"]:
        reasons.append(f"verdict={res['verdict']} not in {expect['verdict_in']}")
    if "resolved" in expect and bool(res["resolved"]) != expect["resolved"]:
        reasons.append(f"resolved={res['resolved']} != {expect['resolved']}")
    if "min_chars" in expect and len(text) < expect["min_chars"]:
        reasons.append(f"chars={len(text)} < {expect['min_chars']}")
    if "contains_any" in expect:
        low = text.lower()
        if not any(tok.lower() in low for tok in expect["contains_any"]):
            reasons.append(f"none of {expect['contains_any']} found")
    return (not reasons, reasons)


def run_one(name: str, script: Path, cases: list, allow_browser: bool, timeout: int) -> list[dict]:
    print(f"\nStrategy: {name}   cases: {len(cases)}   browser: {'off' if allow_browser is False else 'on'}")
    print("=" * 94)
    out = []
    for c in cases:
        res = run_strategy(script, c["url"], allow_browser, timeout)
        ok, reasons = evaluate(c["expect"], res)
        hard = c.get("known_hard", False)
        out.append({"case": c, "res": res, "ok": ok, "reasons": reasons})
        tag = "PASS" if ok else ("hard-fail" if hard else "REGRESSION")
        print(f"[{tag:10}] {c['id']:22} {c['category']:12} "
              f"verdict={res['verdict']:10} {len(res.get('text') or ''):>6}c {res['elapsed']:>5.1f}s")
        if not ok:
            print(f"             why: {'; '.join(reasons)}")
    core = [r for r in out if r["case"]["category"] in CORE]
    front = [r for r in out if r["case"]["category"] not in CORE]
    regressions = [r for r in core if not r["ok"]]
    print("-" * 94)
    print(f"CORE: {sum(r['ok'] for r in core)}/{len(core)}"
          + ("  ❌ REGRESSIONS" if regressions else "  ✅")
          + f"    FRONTIER: {sum(r['ok'] for r in front)}/{len(front)} solved")
    return out


def matrix(all_results: dict[str, list[dict]], cases: list) -> None:
    names = list(all_results)
    by = {n: {r["case"]["id"]: r for r in rs} for n, rs in all_results.items()}
    w = max((len(n) for n in names), default=4)
    print("\n" + "=" * 94)
    print("COMPARISON MATRIX  (✓ pass · ✗ fail)")
    print("-" * 94)
    header = f"{'case':22} {'category':12} " + " ".join(f"{n[:w]:>{w}}" for n in names)
    print(header)
    for c in cases:
        row = f"{c['id']:22} {c['category']:12} "
        cells = []
        for n in names:
            r = by[n].get(c["id"])
            cells.append(f"{'✓' if r and r['ok'] else '✗':>{w}}")
        print(row + " ".join(cells))
    print("-" * 94)
    totals = f"{'TOTAL pass':22} {'':12} "
    totals += " ".join(f"{sum(r['ok'] for r in all_results[n]):>{w}}" for n in names)
    print(totals)


def main() -> int:
    strategies = discover_strategies()
    ap = argparse.ArgumentParser(description="get-page benchmark harness")
    ap.add_argument("--strategy", default="getpage",
                    help=f"one of {list(strategies)} or 'all'")
    ap.add_argument("--category")
    ap.add_argument("--case")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--timeout", type=int, default=150)
    ap.add_argument("--json")
    a = ap.parse_args()

    cases = [c for c in CASES
             if (not a.category or c["category"] == a.category)
             and (not a.case or c["id"] == a.case)]
    if not cases:
        print("no matching cases"); return 1

    selected = list(strategies) if a.strategy == "all" else [a.strategy]
    missing = [s for s in selected if s not in strategies]
    if missing:
        print(f"unknown strategy {missing}; available: {list(strategies)}"); return 1

    all_results = {}
    for name in selected:
        all_results[name] = run_one(name, strategies[name], cases,
                                    allow_browser=not a.no_browser, timeout=a.timeout)

    if len(selected) > 1:
        matrix(all_results, cases)

    if a.json:
        dump = {n: [{"id": r["case"]["id"], "url": r["case"]["url"],
                     "category": r["case"]["category"], "ok": r["ok"],
                     "reasons": r["reasons"], "verdict": r["res"]["verdict"],
                     "chars": len(r["res"].get("text") or ""),
                     "elapsed": round(r["res"]["elapsed"], 1)} for r in rs]
                for n, rs in all_results.items()}
        Path(a.json).write_text(json.dumps(dump, indent=2))
        print(f"\nraw results → {a.json}")

    # Regression gate is based on the get-page strategy only.
    ref = all_results.get("getpage")
    if ref:
        regr = [r for r in ref if r["case"]["category"] in CORE and not r["ok"]]
        return 1 if regr else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
