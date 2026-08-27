---
name: pr-body
description: Use when creating or updating any GitHub pull request — writing or rewriting a PR body/description, about to run `gh pr create` or `gh pr edit`, or finishing a branch whose work needs a PR. Applies to every PR regardless of size, including drafts and stacked PRs.
---

# Composing a PR body

You (the agent that did the work) are the wrong author for parts of this body: your chat context is exactly the contamination a reviewer doesn't want. So you orchestrate — clean-context subagents produce the analysis, one writer composes it, and you only gather facts and post.

**Never write the PR body directly yourself. Never paste chat history or your own summary of the work into any subagent prompt.**

## Target structure

```
<one-sentence lead — what this PR does and why>

Closes #N

## What this does        ← brief list, observable behavior
## Decisions to review   ← omit the section entirely if none found
## Line breakdown        ← category totals table
```

Small PRs get small bodies — a lead sentence, a few bullets, maybe no decisions. The pipeline still runs.

## Phase 0 — gather facts (you)

1. Resolve the base branch; write the full diff and numstat to the scratchpad:
   `git diff <base>...HEAD > <scratchpad>/pr-diff.txt` and `git diff --numstat <base>...HEAD > <scratchpad>/pr-numstat.txt`
2. Resolve the linked issue with `gh` (branch link or ask the user) — verify the number via `gh issue view`, never from git log or memory.
3. Check for an existing PR: `gh pr list --head <branch>`.

## Phase 1 — three parallel subagents (`model: opus`, clean context)

Each prompt gets: the two scratchpad file paths, the issue number, the repo path. Nothing else about the session.

**Decisions agent** — may read the diff, the issue, and any repo code it needs. Instruct it: *"Surface only decisions embedded in this diff that a senior reviewer would genuinely pause on — contracts and interfaces created, tradeoffs taken, blast radius, irreversibility, security. For each: what was chosen, the live alternative, why it matters. Zero findings is a correct answer. Excluded: naming, formatting, style, forced moves, and anything the issue itself already mandates."*

**Classifier agent** — reads numstat, inspects files as needed. Output: total changed lines per category — production code, tests, docs, config/build, generated (lockfiles, build output, fixtures) — splitting mixed files by judgment. **Totals must sum to the numstat total; if they don't, it redoes the arithmetic before returning.**

**Summarizer agent** — reads diff + issue. Output: a brief list of what the PR does, phrased as behavior a reviewer can check ("popups now close on teardown"), never file narration ("modified Map_.js").

## Phase 2 — one writer subagent (clean context)

Prompt: read `~/github/write-like-carson/guides/tech-doc.md` in full, then compose the body from the three payloads using the target structure. Additional rules, verbatim:

- Plain English; every term defined before use; brief.
- Lead with what changed, not how the work went.
- No session narrative, no review-process history, no "we discussed".
- No AI attribution of any kind.
- Line table: `| Category | Lines | % |`, rows sorted descending, omit empty categories.

## Phase 3 — verify and post (you)

1. Spot-check each decision against the actual diff — cut any the diff doesn't support.
2. Check the table sums against numstat.
3. Write the body to a scratchpad file, never the repo.
4. `gh pr create --body-file …` (or `gh pr edit` if a PR exists). Imperative title; follow the repo's title conventions. `Closes #N` stays in the body. Never merge.

## Red flags — stop and restart the phase

| Thought | Reality |
|---------|---------|
| "I'll just write it myself, I know this work best" | Knowing the work best is the problem — that knowledge is chat contamination. Orchestrate. |
| "I'll brief the decisions agent on what we decided" | That makes it a rehash. It gets diff + issue + repo, nothing more. |
| "PR's too small to bother" | Small PR → small body, same pipeline. The classifier and fresh eyes cost one prompt each. |
| "The decisions section feels thin, I'll pad it" | Zero or one decision is a valid, good body. Padding is minutiae. |
| "I'll fix the writer's prose myself" | Re-prompt the writer with the specific fix. One mind owns the prose. |
