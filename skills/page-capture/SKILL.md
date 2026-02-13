---
name: page-capture
description: Captures visual screenshots from web pages using Playwright. ONLY use when the user explicitly needs to SEE what a page looks like visually (e.g., "screenshot", "what does it look like", "show me the page"). Do NOT use for checking status codes, fetching HTML content, or non-visual tasks — use curl or WebFetch for those instead.
allowed-tools: Read, Bash
---

# Page Capture Skill

This skill captures screenshots and rendered HTML from any web page (localhost or external) so you can visually inspect them.

## Setup (First Time Only)

Install dependencies in the skill's own environment:

```bash
cd ~/~/.claude/skills/page-capture && npm install
```

## When to Use

- User explicitly asks to "screenshot" or "capture" a web page
- User wants to debug **visual/styling** issues (layout, colors, rendering)
- User asks "what does the page look like" or "show me the page"

## When NOT to Use

- Checking if a page is up or getting status codes — use `curl -I` instead
- Fetching HTML content or inspecting markup — use `curl` or `WebFetch` instead
- Checking API responses — use `curl` instead
- Any non-visual task where you don't need to see the rendered page

## How to Capture

Run the capture script from the skill directory (uses its own node_modules):

```bash
node ~/.claude/skills/page-capture/scripts/capture-page.js <url> [output-dir]
```

Or using the skill's npm environment explicitly:

```bash
(cd ~/.claude/skills/page-capture && node scripts/capture-page.js <url> [output-dir])
```

Examples:
```bash
# Capture external site
(cd ~/.claude/skills/page-capture && node scripts/capture-page.js https://www.google.com)

# Capture localhost
(cd ~/.claude/skills/page-capture && node scripts/capture-page.js http://localhost:3000/)

# Capture TinaCMS admin page
(cd ~/.claude/skills/page-capture && node scripts/capture-page.js "http://localhost:3000/admin/index.html#/~/themes/agriculture")

# Custom output directory
(cd ~/.claude/skills/page-capture && node scripts/capture-page.js https://example.com /tmp/captures)
```

## After Capture

Output files are named `{domain}_{timestamp}.png` and `{domain}_{timestamp}.html` (e.g., `localhost_2026-02-05-14-30-00.png`). The script prints the paths — use them in the steps below.

**Always** do both of the following after a successful capture:

1. **Read the screenshot** so you can see and describe it:
   ```
   Read /tmp/{domain}_{timestamp}.png
   ```

2. **Open the screenshot** so the user can see it too:
   ```bash
   open /tmp/{domain}_{timestamp}.png
   ```

3. **Rendered HTML** - Optionally inspect the DOM structure:
   ```
   Read /tmp/{domain}_{timestamp}.html
   ```

## Quick Screenshot Only

For just a screenshot without HTML:

```bash
npx playwright screenshot <url> /tmp/screenshot.png --full-page
```

## Tips

- The script waits for `networkidle` to ensure async content loads
- Hash URLs (`#/path`) work correctly for SPAs
- Default viewport is 1920x1080
- Screenshots are full-page by default
