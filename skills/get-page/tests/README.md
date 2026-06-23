# get-page benchmark

A fixed bed of real, difficult URLs (`cases.py`) collected from live sessions.
Run the same cases against different implementations to see exactly which sites
each approach wins.

## Run

```bash
./benchmark.py                      # all cases, current get-page, browser on
./benchmark.py --no-browser         # skip the slow browser rung
./benchmark.py --category js_shell  # one group
./benchmark.py --case mouser        # one site
./benchmark.py --json results.json  # dump raw results for diffing approaches
```

The browser rung makes a full run slow (hard blocks + HTTP/2 timeouts take up to
the per-case `--timeout`, default 150s). Use filters while iterating.

## How cases are judged

- **CORE** (`baseline`, `pdf`, `hard_block`, `not_found`) — get-page's actual
  job. A failure here is a **regression**; the runner exits non-zero.
  - `hard_block` passes when the site is *correctly flagged* as a block
    (verdict `antibot`/`blocked`, `resolved=false`) — not when it's bypassed.
- **FRONTIER** (`http2_crash`, `js_shell`, marked `known_hard`) — sites no
  current approach cracks: anti-bot blackholes and client-rendered price grids.
  These are *expected* to fail today; they're the scoreboard for improvements.

## Adding a new approach

The whole point: keep `cases.py` fixed, swap the implementation. Add a function
to `benchmark.py` with the strategy signature and register it in `STRATEGIES`:

```python
def strat_trafilatura(url, allow_browser, timeout) -> dict:
    # return {"verdict","trail","text","resolved","elapsed","error"}
    ...

STRATEGIES["trafilatura"] = strat_trafilatura
```

Then compare on the identical bed:

```bash
./benchmark.py --strategy get-page    --json out-getpage.json
./benchmark.py --strategy trafilatura --json out-trafilatura.json
```

Candidate approaches to benchmark next: **trafilatura** (extraction),
**MarkItDown** / **docling** (PDF + HTML→markdown), **crawl4ai** (render +
anti-bot, already used in `accelerated-discovery`). The hard anti-bot blocks
(Mouser/Digikey/oemsecrets) realistically need a paid service (Zyte, ScraperAPI,
Bright Data) — worth a strategy stub to confirm, not local code.
