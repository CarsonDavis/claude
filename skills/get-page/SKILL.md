---
name: get-page
description: Use when fetching a web page fails or returns unusable content — WebFetch/curl/requests gives a 403/401 block, 429 rate-limit, an empty or JS-rendered page (SPA shell, missing body text), a Cloudflare/anti-bot challenge, or garbled/binary output. Escalates through HTTP → TLS-impersonation → headless browser to get the real content and extract it as clean markdown or structured data.
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
Cap at HTTP-only (skip the browser) with `--no-browser`.

## The ladder

| Rung | What it does | Beats |
|---|---|---|
| smart | httpx + real browser headers | default-UA blocks (most common) |
| diagnose | classifies the failure, picks next rung | routing |
| impersonate | curl_cffi TLS-fingerprint spoof | anti-bot 403s, no browser |
| browser | Playwright + stealth, scroll-to-load | true JS-rendered pages |

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
- **Browser rung is lazy.** Playwright is pulled in only when the browser rung
  is actually reached. The Chromium binary is a one-time download — if missing,
  the tool prints the exact command:
  `uv tool run --with playwright playwright install chromium`.
- **Single page only.** No crawling/pagination by design — fetch one URL, get
  clean content. For authenticated pages, the browser rung can be extended with
  a persistent profile (not built in).
- **Built-in politeness.** `auto` honors `429` `Retry-After` with backoff.

## Design

See `docs/2026-06-21-get-page-design.md` for the full rationale, the failure
taxonomy, and the patterns distilled from prior scraping projects.
