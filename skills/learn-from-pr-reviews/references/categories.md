# Review dimensions

The categories a verdict's `category` field must use. They mirror the review
pipeline in the llm-conventions repo (`standard-artifacts/review.md`,
https://github.com/NASA-IMPACT/llm-conventions) so the distilled draft drops
straight into that framework. Pick the single best fit; use `emergent` only when
none fit.

| Category | What it covers | Example comment |
|---|---|---|
| `project-alignment` | The change pulls against the project's direction, vision, or how the repo actually works; duplicates an existing capability; ignores a documented interaction/coupling. | "We already have a layer registry for this — don't add a second one." |
| `org-convention-security` | Wider-org security/architecture rules that hold across every project: auth (OIDC, no long-lived keys), no public S3, secret handling, infra patterns, dependency/supply-chain concerns. | "Don't commit this token — use the OIDC role." |
| `craftsmanship` | Ordinary good-reviewer concerns: maintainability, sound architecture, no unrequested bloat, naming, typing, error handling, dead code, sound abstractions. | "This should be typed; `any` hides real bugs here." |
| `test-quality` | Tests missing, or present but not actually exercising the intended behavior; brittle/false-confidence tests; missing edge cases. | "This test passes even if the handler never runs — assert the side effect." |
| `doc-freshness` | A change left its docs stale, or docs/comments need updating to match the code; README/ADR/tutorial drift; comment style/usefulness conventions. | "Update the ADR — this supersedes the decision in section 3." |
| `emergent` | A real, generalizable review lesson that none of the above capture. Use sparingly; if it recurs, it's a signal we're missing a named dimension. | (varies) |

## Substantive vs. not

Mark `substantive: false` (and leave `lesson` empty) for:
- Pure style/formatting a linter would catch, trivial nits, typos.
- Logistics: "rebase", "squash these", "CI is red", "merge main".
- Praise / acknowledgement / chit-chat with no rule in it.
- Questions that never resolved into a guideline.

When unsure whether a *future* reviewer of a *different* PR would care about the
underlying rule, mark `false`. The corpus is meant to be small and sharp.
