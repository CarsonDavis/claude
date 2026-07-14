// Phase 3 — per-thread verdict fan-out.
//
// Invoke via the Workflow tool, once per batch (see batching note below):
//   Workflow({ scriptPath: ".../phase3-verdict.workflow.js",
//              args: { dir: "<abs>/review-mining/<slug>/03-input",
//                      start: 0, count: 900,
//                      schema: <parsed contents of references/verdict-schema.json> } })
//
// Runs one subagent (Sonnet by default) per thread record in the slice [start, start+count).
// Each agent reads its own rec-NNNNN.json, judges it, and returns a
// schema-validated verdict. The workflow returns the array of verdicts; the
// caller appends it to 03-verdicts.jsonl.
//
// BATCHING: a single workflow can spawn at most ~1000 agents over its lifetime.
// For repos with more thread records than that, invoke this workflow repeatedly
// with start = 0, 900, 1800, ... (count = min(900, total-start)) and concatenate
// the returned arrays. The split-threads.sh helper prints the total record count.
//
// SCHEMA: passed in via args.schema (the canonical copy lives in
// references/verdict-schema.json) so there is a single source of truth — the
// workflow does not embed its own copy.

export const meta = {
  name: 'learn-from-pr-reviews-phase3',
  description: 'Judge each PR review comment thread (substantive? acted-on? lesson?) with a Sonnet subagent',
  phases: [{ title: 'Verdict', detail: 'one Sonnet agent per comment thread', model: 'sonnet' }],
}

const PROMPT = (path) => `You are mining ONE code-review comment thread from a real pull request to extract reusable reviewer wisdom.

Read the JSON record at this absolute path:
${path}

The record contains:
- pr, thread_id, url, source ("inline" | "review-summary" | "issue-comment")
- comments[]: the comment chain (author, body, createdAt)
- resolved / outdated (inline only): thread resolution + whether the code under it changed
- code_window or diff_hunk: the code the reviewer was looking at
- post_comment_delta: the git diff of that file AFTER the comment (empty = file unchanged afterward)
- delta_truncated: true if post_comment_delta was cut off at a line cap (the diff is INCOMPLETE)
- renamed_to: if non-null, the commented file was MOVED to this path after the comment (strong evidence a "move/relocate/reorganize this file" request was acted on)
- pr_commits_after: commit summaries landed after the comment
- code_context: "full" | "partial" | "none"

YOUR JUDGEMENT (output via the StructuredOutput tool, matching the schema exactly):

1. substantive (bool): true ONLY if there is a generalizable review lesson — correctness, design, a repo/org convention, security, testing, maintainability, or docs. Mark FALSE for: pure style/formatting a linter catches, trivial nits, typos, logistics ("rebase", "squash", "CI red"), praise, chit-chat, or questions that never became a guideline. When unsure whether a reviewer of a DIFFERENT future PR would care about the underlying rule, mark false. Be strict — the corpus must stay small and sharp.

2. category: best single fit —
   - project-alignment: pulls against project direction/vision/how-the-repo-works; duplicates existing capability; ignores a documented coupling.
   - org-convention-security: cross-project security/architecture rules (OIDC, no long-lived keys, no public S3, secrets, infra/supply-chain).
   - craftsmanship: maintainability, architecture, no unrequested bloat, naming, typing, error handling, dead code, abstractions.
   - test-quality: tests missing, or present but not exercising intended behavior; brittle/false-confidence; missing edge cases.
   - doc-freshness: stale docs, README/ADR/tutorial drift, comment-style/usefulness conventions.
   - emergent: a real generalizable lesson none of the above capture (use sparingly).

3. verdict — what ACTUALLY happened, judged from EVIDENCE not just words:
   - addressed: post_comment_delta or resolution shows the requested change was made.
   - rejected: author/thread explicitly declined.
   - ignored: no reply, thread unresolved, and no relevant change in the delta.
   - acknowledged-no-change: discussed/agreed but code intentionally left as-is.
   - unclear: evidence insufficient.
   Use post_comment_delta as the primary signal: a delta that touches the discussed code = likely addressed; an EMPTY delta + unresolved = likely ignored. If renamed_to is non-null the file was relocated after the comment — when the comment asked to move/reorganize the file and the new path satisfies that request, that is "addressed" (do NOT read the rename's whole-file deletion as the file being removed).
   HARD RULES — the record's structured fields OVERRIDE your impression of the prose:
   - If resolved is true, the thread was RESOLVED on GitHub: NEVER output "ignored". Pick "addressed" if the delta shows the change, otherwise "acknowledged-no-change" or "unclear".
   - Output "ignored" ONLY when resolved is false AND post_comment_delta is empty (or clearly unrelated to the comment). If the delta is non-empty but you cannot tell whether it addresses THIS specific comment, output "unclear" — never "ignored".

4. confidence: high/med/low. Use low when code_context is partial or none, OR when delta_truncated is true (you cannot see the whole change, so an "addressed/ignored" call is uncertain).

5. lesson: ONE generalizable reviewer rule, phrased to fit a review checklist for ANY future PR (not specific to this file). Empty string "" if substantive is false.

6. quote: the most telling sentence(s) from the original comment, verbatim, <=300 chars.

Copy pr, thread_id, url, source, and code_context VERBATIM from the record.`

phase('Verdict')

const cfg = typeof args === 'string' ? JSON.parse(args) : (args || {})
if (!cfg.dir) throw new Error('args.dir is required')
if (!cfg.count) throw new Error('args.count is required')
if (!cfg.schema) throw new Error('args.schema is required (pass the parsed verdict-schema.json)')

const start = Number(cfg.start || 0)
const count = Number(cfg.count)
const model = cfg.model || 'sonnet'  // Sonnet is better-calibrated on ambiguous "acted-on?" cases; pass args.model to override (e.g. 'haiku' to cut cost)
const pad = (i) => String(i).padStart(5, '0')
const paths = Array.from({ length: count }, (_, k) => `${cfg.dir}/rec-${pad(start + k)}.json`)

const verdicts = await parallel(
  paths.map((p, k) => () =>
    agent(PROMPT(p), { label: `verdict:rec-${pad(start + k)}`, schema: cfg.schema, model })
  )
)

const ok = verdicts.filter(Boolean)
log(`Batch [${start}, ${start + count}): ${ok.length}/${count} verdicts (${ok.filter(v => v.substantive).length} substantive)`)

// Fail loud rather than return a short batch: a dropped record must never pass
// silently just because the orchestrator forgot to diff counts. Workflow resume
// reuses the cached successes, so re-running only re-does the failed agents.
const failed = paths.filter((_, i) => !verdicts[i])
if (failed.length) {
  throw new Error(
    `Batch [${start}, ${start + count}): ${failed.length}/${count} agents returned no verdict. ` +
    `Refusing to return a short batch so records can't be silently lost. ` +
    `Failed: ${failed.map(p => p.split('/').pop()).join(', ')}. ` +
    `Re-run this batch (resume reuses cached successes).`
  )
}
return ok
