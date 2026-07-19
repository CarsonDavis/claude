---
name: review-formatter
description: Use ONLY when the user explicitly asks to format code-review findings into their plain-English review style, or invokes /review-formatter. Do NOT invoke automatically after producing a review, finishing a code review, or listing bugs — this is on-demand formatting, never triggered by a review merely completing.
---

# Review Formatter

## Overview

Formats code-review findings into Carson's house review style. The defining move: **every finding leads with a plain-English explanation and its stakes, and all code-level precision is quarantined into a separate technical block.** A reader who cannot read the code should still understand every finding and why it matters.

## When to Use

- ONLY when explicitly asked: "format this review", "put these findings in my review format", "write this up as a review", or `/review-formatter`.
- **NOT** automatically when a review or `/code-review` finishes, or when you've just listed bugs. Producing findings ≠ formatting them. Wait to be asked — this skill is on-demand only.

## Document structure

```
# PR #<N> Review — <title>

**Branch:** `<head>` → `<base>`
**Author:** <name> · **Closes** #<issue>
**Reviewed:** <date> (<how — e.g. 5-agent parallel review; two highest bugs re-verified by hand>)

> Optional blockquote preamble: merge context, stacking, or why this PR
> matters disproportionately. Omit if there's nothing to flag.

---

<one section per finding, separated by --->

---

## What's good        (brief, genuine positives — decoupling preserved, clean deletes, etc.)
## Verdict            (ship / block / merge-with-conditions)
```

## Per-finding structure

Every finding has exactly these parts, in this order:

```
## <emoji> <Category> N — <short title> *(status)*

**Plain English:** One paragraph, **zero code identifiers**. What the code does,
what goes wrong, and the user-visible consequence — in ordinary language a
non-coder or a busy lead grasps on a single read. Analogies welcome.

**Why it matters:** One paragraph on stakes: severity, blast radius, why it's
easy to miss, and — characteristically — how it bears on the project's
north-star (e.g. plugin decoupling, the API boundary).

**Technical detail:**
- exact `path/to/file.ext:line-range` references, function names, the mechanism
- **Fix:** <concrete fix>                    ← for bugs
- **Suggested direction:** <optioned proposal>  ← for design findings (softer, not prescriptive)
```

Category words: **Bug** / **Finding** / **Design** / **Minor**. Optional italic status tag after the title: `*(confirmed)*`, `*(verified)*`, `*(race)*`, `*(pre-existing)*`.

## Severity scale (high → low)

| Emoji | Meaning |
|-------|---------|
| 🔴 | critical / confirmed correctness bug |
| 🟠 | high-priority bug |
| 🟡 | design concern / medium |
| 🟢 | minor |
| ⚪ | cleanliness / vestigial / dead code / pre-existing |

Order findings most-severe first.

## The one rule that makes it work

**Plain English and Why-it-matters contain no file paths and no code identifiers.** Every symbol, path, and line number lives *only* in Technical detail. If a reader who can't read code can't follow the first two paragraphs, rewrite them — that separation is the entire point of the format. Bugs get a prescriptive **Fix:**; design/opinion findings get the softer **Suggested direction:** so they read as proposals, not orders.

## Worked example

```
## 🔴 Bug 1 — Panel ordering breaks when float and edge panels are mixed *(confirmed)*

**Plain English:** Floating panels are allowed to skip the "priority" number that
decides stacking order. But the code that sorts panels assumes every panel has that
number. When a float panel (no priority) sits next to a normal edge panel (has one),
the sort math produces garbage and panels land in an unpredictable order. It looks
fine in some configs and randomly wrong in others — a nasty intermittent bug.

**Why it matters:** This is a correctness bug in the core layout engine that only
shows up in exactly the mixed-panel configs this feature is meant to enable.
Non-deterministic ordering is hard to reproduce and erodes trust in the layout system.

**Technical detail:**
- `PanelManager_.ts:274` and `:285` both sort with `(a,b) => a.config.priority - b.config.priority`.
- The validator makes `priority` optional for float panels (`DashboardConfigValidator.js:205-217`).
- So a float arrives with `priority === undefined`; `number - undefined` is `NaN`, and
  `Array.sort` treats a `NaN` comparator as "leave order unchanged" → effectively unsorted.
- **Fix:** normalize before subtracting, e.g. `(a.config.priority ?? Infinity) - (b.config.priority ?? Infinity)`.
```

## Common mistakes

- **Leading with the technical detail** or restating the diff line-by-line — the Plain English must stand alone and come first.
- **Code identifiers in Plain English** — no `foo()`, no paths, no `NaN`. Move them down.
- **Prescriptive "Fix:" on a design/taste finding** — use "Suggested direction:" so it reads as a proposal.
- **No positives** — always close with a brief, genuine "What's good".
- **Auto-formatting when nobody asked** — this skill is explicit-invocation only.
