# get-page — benchmark rationale & findings

> Reference for future devs. NOT loaded into the skill's context window (only
> `SKILL.md` is). Read this before changing the fetch ladder or extraction.

## Why this benchmark exists

get-page is meant to be the fallback any agent reaches for when a normal fetch
fails. Two questions came up that we refused to answer by hand-waving:

1. **Are we reinventing wheels?** Mature OSS libraries (trafilatura, crawl4ai,
   MarkItDown, docling) already do extraction / rendering / anti-bot.
2. **Does our code actually work on the hard cases**, or only on easy pages?

So we built a fixed bed of **real, difficult URLs** collected from a live
BOM-sourcing session (electronics distributor/aggregator pages — anti-bot,
JS-rendered, PDFs, 404s) and ran competing implementations against it. Keep the
cases fixed, swap the implementation, compare. See `README.md` to run it.

## What we tested

| Strategy | What it is |
|---|---|
| `getpage` | our tiered HTTP → TLS-impersonation → browser ladder + diagnosis |
| `trafilatura` | OSS main-content extraction (HTTP only, no JS) |
| `crawl4ai` | OSS stealth headless render (patchright), JS + anti-detection |

Cases are split into **CORE** (baseline, pdf, hard_block, not_found — get-page's
actual job; a failure is a regression) and **FRONTIER** (`http2_crash`,
`js_shell` — client-rendered grids and anti-bot blackholes nothing easily cracks).

## Key findings

**1. No single approach wins — routing and rendering are different jobs.**

- `getpage` owned CORE (9/9): status handling, PDF extraction, block/404
  classification. But frontier 0/6 — it can't render client-side data.
- `crawl4ai` alone got 3/6 frontier but *broke* CORE (6/9): it rendered Mouser's
  denial page and called it "usable", and turned a soft-404 into content. It has
  no routing/diagnosis layer.
- `trafilatura` alone was weak (2 total): it's an extractor, not a fetcher, and
  returns nothing on JS-rendered pages (the data isn't in the HTML).

**2. The win was a hybrid, not a replacement.**

Use crawl4ai as get-page's **browser rung**, with get-page's
diagnosis/PDF/404/block layer kept on top. That layer is precisely what catches
the rendered block page crawl4ai alone mislabels. Result:

```
                    CORE        FRONTIER (6)
original getpage    9/9 ✅       0/6
crawl4ai alone      6/9 ❌       3/6
HYBRID (shipped)    9/9 ✅       4/6   ← arrow, findchips, lcsc, tme
```

**3. A second, subtler fix was needed for the JS grids.**

The client-rendered price grids (octopart/findchips/lcsc/tme) return HTTP 200
with *lots of nav boilerplate* but no real data, so they parsed as "usable" and
never escalated. Measuring raw visible text didn't flag them. The fix
(`_main_content_len` in `get_page.py`): trigger a browser "second opinion" when
the **readability main-content** is thin (chrome excluded) AND `<script>` markers
are present AND the verdict was "usable". Real articles clear the bar; shells
don't. This routed the grids to the crawl4ai rung and recovered 3 of 4.

## Honest limits (don't expect these to "just work")

- **Hard anti-bot blocks** (Mouser/PerimeterX, Digikey/Cloudflare, oemsecrets):
  correctly *flagged* as blocked, but **unreachable with any free/local tool**.
  Real prices live exactly on these sites. Beating them needs a paid service
  (Zyte, ScraperAPI, Bright Data) — deliberately out of scope.
- **Anti-bot is non-deterministic.** octopart returned 23K chars one run and was
  blocked (487c) the next. Frontier numbers wobble ±1–2 run to run; re-run the
  frontier a few times before trusting a delta.
- **`tme` reports verdict `antibot` yet yields the data** — a block signature
  matched somewhere in a page that still rendered its catalog. Verdict labels on
  partially-blocked pages are noisy; trust `resolved` and content, not the label.

## If you change the fetch/extract path

Re-run the bed and confirm **CORE stays 9/9** (that's the regression gate; the
runner exits non-zero on a CORE failure for the `getpage` strategy). Frontier
gains are bonus. To evaluate a new library, add a `strategies/<name>.py` and run
`./benchmark.py --strategy all` — see `README.md`.
