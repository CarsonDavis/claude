# Design: `learn-from-pr-reviews` skill

> **Status:** approved design, ready for implementation planning.
> Turns a repository's entire PR-review history into (a) a verified, categorized
> "review-wisdom corpus" and (b) a **draft** `review.md` + review-agent prompt.
> Repo-agnostic; first test target is `NASA-IMPACT/MMGIS` (local clone at
> `/Users/cdavis/github/MMGIS`).

## Purpose

A reviewer's accumulated judgement lives only in scattered PR comments. This skill
mines that history and distills it into a reusable review artifact — the §3 "Review"
core document and pipeline defined in the **llm-conventions** repo
(`standard-artifacts/overview.md` + `standard-artifacts/review.md`,
https://github.com/NASA-IMPACT/llm-conventions).

The central insight: **a comment existing does not mean it was meaningful, and a
comment being made does not mean it was acted on.** A useful corpus must separate
substantive review feedback from nits, and addressed feedback from
ignored/rejected feedback. We judge both against *actual code*, not just the
comment text.

## Scope decisions (locked)

- **End deliverable:** verified/categorized corpus **AND** an auto-drafted
  `review.md` checklist + review-agent prompt, clearly marked DRAFT for human edit.
- **Comment sources:** all three, each finding tagged by source —
  (1) inline code-review comments, (2) PR-level review summaries
  (approve / request-changes bodies), (3) issue-conversation comments.
- **PR scope:** all states — merged, closed-unmerged, open. Closed-unmerged PRs
  often hold the richest "we rejected this and why" wisdom.
- **Fork boundary is automatic:** `gh pr list` against the fork returns only PRs
  opened in the fork org, not upstream history. No special filtering needed.

## Architecture

A **Skill** (the durable, point-it-at-any-repo artifact) that runs a 5-phase
pipeline. Phases have deliberately different cost profiles: data collection is
pure deterministic scripting (no LLM); per-comment judgement fans out to small
fast subagents; synthesis runs once on a strong model.

| Phase | What | Executor | Cost |
|---|---|---|---|
| 1. Enumerate | List every PR (all states) → `01-prs.json` | `gh` script, no LLM | ~free |
| 2. Dump + enrich | Per PR: fetch all comments/reviews + thread resolution + commit log; per inline comment, extract code window + post-comment delta → `02-threads/PR-<n>.json` | `gh`/GraphQL + local `git`, no LLM | ~free |
| 3. Verdict | Per comment thread, a **Sonnet** subagent emits a structured verdict | Workflow fan-out | bulk, parallel |
| 4. Categorize | Group substantive verdicts into review dimensions → corpus | orchestrator (strong model) | one pass |
| 5. Distill | Draft `review.md` + agent prompt (marked DRAFT) | orchestrator | one pass |

### Why Skill-calls-Workflow (not one flat session, not loose subagents)

- A flat session can't hold 42 PRs of comments + code at once, and would pay Opus
  rates to read diffs a smaller Sonnet subagent can judge.
- The Workflow tool gives deterministic fan-out, automatic concurrency caps,
  schema-validated returns, and resume-on-failure — better than hand-dispatching
  agents. `SKILL.md` explicitly instructs the Workflow call (that is the opt-in).

## Phase 1 — Enumerate

`scripts/enumerate-prs.sh <owner/repo>`:
- `gh pr list --state all --limit <N> --json number,title,state,author,createdAt,mergedAt,baseRefName,headRefName`
- Writes `review-mining/<owner-repo>/01-prs.json`.
- No LLM.

## Phase 2 — Dump threads + code-context enrichment

`scripts/fetch-pr-threads.sh <owner/repo> <local-repo-path>`, run per PR. All
deterministic; no LLM. For each PR `<n>`:

**Comment/review collection (all `--paginate`d → no caps):**
- Inline comments: `gh api repos/{owner}/{repo}/pulls/{n}/comments --paginate`
  (flat, fully paginated; carries `id`, `original_commit_id`/`commit_id`, `path`,
  `original_line`/`line`, `diff_hunk`, `in_reply_to_id`, `body`, `user`,
  `created_at`). Threads are reconstructed by grouping on `in_reply_to_id // id`
  (root = earliest comment) — verified to match GitHub's authoritative GraphQL
  threading exactly. REST is used (not GraphQL) for the comment data because it
  paginates trivially and its `original_line`/`original_commit_id` resolve
  *outdated* comments where GraphQL returns null.
- Review summaries: `gh api .../pulls/{n}/reviews --paginate` (state + body;
  empty bodies skipped).
- Issue-conversation comments: `gh api .../issues/{n}/comments --paginate`.
- Thread resolution: GraphQL `pullRequest.reviewThreads { isResolved, isOutdated }`
  **paginated** (`first:100, after:$endCursor` + `gh --paginate`), reduced to a
  map `root-comment-databaseId → {resolved, outdated}` and joined onto the REST
  threads. GraphQL is used only for this (REST doesn't expose resolution).
- PR commit log: `gh api .../pulls/{n}/commits --paginate` → ordered SHAs;
  `pr_head_sha` = last commit.

**Code-context enrichment (local git, per inline comment):**
1. Detect which local remote points at the repo (match the remote whose URL
   contains `<owner/repo>`; fall back to `origin`), then once per run make all PR
   commits resolvable: `git fetch <remote> "+refs/pull/*/head:refs/remotes/pr/*"`.
2. **Code window at comment-time:** `git show <commit>:<path>` written to a temp
   file (no pipe → no SIGPIPE), sliced to ±50 lines around the commented line —
   the code exactly as the reviewer saw it.
3. **Post-comment delta:** `git diff <commit> <pr_head_sha> -- <path>`
   (`--find-renames`), capped at 400 lines via `head … || true` (the `|| true`
   prevents a SIGPIPE-induced `set -e` abort on large diffs). Empty delta +
   unresolved thread = strong "ignored"; delta touching the region = "addressed".

Both are written into the thread record so phase-3 agents read grounded code from
disk with no extra API calls (~1–2k tokens per comment).

**Graceful degradation (tag and continue, never silently drop):**
- Commit unresolvable (force-push/orphaned), path missing/renamed at that commit,
  or blob binary/empty → fall back to stored `diff_hunk`, set
  `code_context: "partial"` (binary detected via `grep -Iq .` on the temp blob).
- Issue/review comments have no commit/path → no window; judged on text +
  subsequent commit summaries + replies, set `code_context: "none"`.

Output: `review-mining/<owner-repo>/02-threads/PR-<n>.json` — one record per
comment thread, each self-contained (comment chain + resolution + code window +
delta + commit summaries).

## Phase 3 — Per-thread verdict (Workflow fan-out, Sonnet)

The work-list is every thread record across all `02-threads/PR-*.json`,
flattened by `scripts/split-threads.sh` into one `03-input/rec-NNNNN.json` per
record (one jq + one awk pass, so it scales to thousands). A `parallel()`
Workflow fans out one Sonnet subagent per record, in **batches of ≤900** (a single
workflow's lifetime agent cap is ~1000) — the orchestrator invokes the workflow
with `start = 0, 900, …` and appends each batch's results, then confirms the
verdict count equals the record count. The structured-output **schema is passed
in via `args.schema`** from `references/verdict-schema.json` (single source of
truth — the workflow embeds no copy). Each agent emits:

```json
{
  "pr": 108,
  "thread_id": "…",
  "url": "https://github.com/…",
  "source": "inline | review-summary | issue-comment",
  "substantive": true,
  "category": "project-alignment | org-convention-security | craftsmanship | test-quality | doc-freshness | emergent",
  "verdict": "addressed | rejected | ignored | acknowledged-no-change | unclear",
  "confidence": "high | med | low",
  "code_context": "full | partial | none",
  "lesson": "one-line generalizable reviewer rule",
  "quote": "the original comment text"
}
```

- `substantive: false` → nit/noise/logistics. Kept in raw verdicts (auditable) but
  excluded from the corpus. **No silent dropping** — phase 4 logs the discard count.
- `lesson` is the gold: it generalizes a specific comment into a reusable rule.
- The agent judges *substance* from the code window and *acted-on* from the
  delta + resolution + `outdated` flag + author replies.

Aggregated to `review-mining/<owner-repo>/03-verdicts.jsonl`.

## Phase 4 — Categorize → corpus

Orchestrator (strong model) reads `03-verdicts.jsonl`, keeps `substantive: true`,
and groups by category — dimensions taken straight from `review.md`:
project-alignment, org-convention/security, craftsmanship, test-quality,
doc-freshness, plus an **emergent** bucket for patterns those don't capture.

Output `review-mining/<owner-repo>/04-corpus.md`: per category, the deduped lessons
with PR links, frequency counts, and verdict mix (how often the team actually
enforced each rule). Header reports totals: threads analyzed, substantive vs.
discarded, confidence distribution, `code_context` coverage.

## Phase 5 — Distill → draft review artifact

Orchestrator drafts `review-mining/<owner-repo>/05-review-draft.md`:
- A `review.md`-style checklist grouped by the same dimensions.
- A review-agent prompt skeleton aligned to the `review.md` pipeline.
- Every section clearly marked **DRAFT — human review required**, with the
  supporting PR links inline so a human can verify each rule against its evidence.

## File layout

```
skills/learn-from-pr-reviews/
  SKILL.md                  # orchestration instructions (invokes Workflow in phase 3)
  scripts/
    enumerate-prs.sh           # phase 1
    fetch-pr-threads.sh        # phase 2 (gh REST + paginated GraphQL resolution + local git)
    split-threads.sh           # phase 3 prep (flatten -> 03-input/rec-NNNNN.json)
    phase3-verdict.workflow.js # phase 3 Workflow template (Sonnet fan-out, batched)
  references/
    verdict-schema.json     # phase 3 structured-output schema (single source of truth)
    categories.md           # the review dimensions + definitions

review-mining/<owner-repo>/  # OUTPUTS — gitignored (do not commit mined repo data)
  01-prs.json
  02-threads/PR-<n>.json
  03-verdicts.jsonl
  04-corpus.md
  05-review-draft.md
```

`review-mining/` is added to `.gitignore`.

## v1 simplifications (YAGNI)

- Fixed ±50-line window, not language-aware function extraction.
- Single repo per run (no multi-repo aggregation yet).
- Sonnet for phase-3 verdicts (chosen over Haiku after an A/B showed it is better
  calibrated on ambiguous "addressed vs. ignored" cases); pass `args.model` to override.

No silent caps remain: comments/reviews/commits are fully paginated, the
resolution query is paginated, PR enumeration warns if it hits its limit, and
phase 3 batches past the workflow agent cap. A diff longer than 400 lines is the
one intentional truncation (the reviewed region is near the comment anyway).

## Success criteria

- Running the skill against MMGIS produces all five artifacts without manual steps.
- Each corpus lesson traces to a real PR comment via its URL.
- Spot-checking corpus entries against the actual PRs confirms the `verdict`
  (addressed/ignored/rejected) matches what the code history shows.
- Nits are correctly excluded from the corpus, and the discard count is reported.
