---
name: get-page
description: Use when fetching a web page fails or returns unusable content — WebFetch/curl/requests gives a 403/401 block, 429 rate-limit, an empty or JS-rendered page (SPA shell, missing body text), a Cloudflare/anti-bot challenge, garbled/binary output, or a PDF you need as text. Escalates through HTTP → TLS-impersonation → headless browser to get the real content and extract it as clean markdown or structured data.
---

# get-page

Tiered escalation toolkit for fetching stubborn web pages. When a normal fetch
fails, this walks an escalation ladder until it gets usable content, then
extracts it. Rungs 0–2 are HTTP-only and instant; the browser rung is
break-glass and self-installs only when reached.

## When to use

Reach for this the moment a page won't come down cleanly:
- `403`/`401` block, or content that's clearly a bot wall
- `429` rate-limiting
- Empty body / missing content — a JavaScript-rendered SPA
- Cloudflare / "Just a moment…" / "Enable JavaScript" challenge
- Garbled or binary output (encoding/compression mismatch)

## Quick start

One command does the whole ladder and returns clean markdown:

```bash
~/.claude/skills/get-page/get-page auto <url>
```

It escalates only as far as needed and prints a provenance trail, e.g.
`<!-- get-page: <url> | smart → blocked | impersonate → usable -->`.

Formats: `--format md` (default) · `json` (markdown + jsonld + metadata) · `raw`.
Cap at HTTP-only (skip browsers) with `--no-browser`. Skip only the deepest
headful rung (no visible window) with `--no-headful`.

**Trust the verdict.** If the ladder never reaches usable content, `auto`
prints a `⚠` banner and exits non-zero — the body is likely a block/challenge
page, not the real content. Don't treat a warned result as the answer.

**PDFs** are handled automatically: `auto`/`readable` on a PDF URL detect it and
return extracted text instead of choking on binary.

## The ladder

| Rung | What it does | Beats |
|---|---|---|
| smart | httpx + real browser headers | default-UA blocks (most common) |
| diagnose | classifies the failure, picks next rung | routing |
| impersonate | curl_cffi TLS-fingerprint spoof | anti-bot 403s, no browser |
| browser | crawl4ai (stealth headless render) | JS-rendered pages, some anti-bot |
| nodriver | undetected **headful** Chrome (last resort) | Cloudflare that beats crawl4ai/Playwright |

`auto` runs these for you. Use individual subcommands to compose your own flow.

## Subcommands

```bash
get-page auto <url> [--format md|json|raw] [--no-browser]
get-page fetch <url> [--rung smart|impersonate|browser]   # raw HTML to stdout
get-page diagnose <url>                                    # JSON: why it failed
get-page readable <url|file|->                             # HTML → markdown
get-page jsonld   <url|file|->                             # application/ld+json
get-page select   <url|file|-> "<css>"                     # elements by selector
get-page meta     <url|file|->                             # title/OG/links
```

Extractors take a URL, a file path, or `-` for stdin, so rungs and extractors
pipe together without re-fetching:

```bash
get-page fetch --rung impersonate <url> | get-page jsonld -
```

Run `get-page <command> --help` for flags.

## Notes

- **Zero setup.** `uv` reads the inline dependency header and manages an
  isolated environment automatically on first run. Nothing to `pip install`.
- **Browser rungs are lazy.** crawl4ai + nodriver are pulled in only when a
  browser rung is reached, then cached. crawl4ai (headless) also fires as a
  "second opinion" when an HTTP result looks usable but is suspiciously thin
  with `<script>` markers (client-rendered listing grids).
- **nodriver is the deepest, last-resort rung** and runs **headful** (a visible
  Chrome window) — that is what defeats Cloudflare where headless crawl4ai and
  even headful Playwright/patchright get a challenge page. It only fires when
  every rung above still failed. `--no-headful` disables it; it needs Google
  Chrome installed.
- **Single page only.** No crawling/pagination by design — fetch one URL, get
  clean content. For authenticated pages, the browser rung can be extended with
  a persistent profile (not built in).
- **Built-in politeness.** `auto` honors `429` `Retry-After` with backoff.

## For maintainers

Benchmark, rationale, and the OSS-approach comparison that shaped the ladder live
in `tests/` (`FINDINGS.md`, `README.md`) — not loaded here. Re-run the bed and
keep CORE at 9/9 before changing the fetch/extract path.
