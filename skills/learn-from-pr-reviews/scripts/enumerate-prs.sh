#!/usr/bin/env bash
#
# Phase 1 — Enumerate every PR in a repository (all states).
#
# Usage:  enumerate-prs.sh <owner/repo> [limit]
# Output: review-mining/<owner-repo>/01-prs.json
#
# Pure data collection. No LLM. The fork boundary is automatic: `gh pr list`
# against a fork returns only PRs opened in the fork org, not upstream history.

set -euo pipefail

REPO="${1:?usage: enumerate-prs.sh <owner/repo> [limit]}"
LIMIT="${2:-100000}"   # effectively "all"; we warn below if a repo actually hits it

# Resolve output dir relative to the repo root that contains this script's parent.
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SLUG="${REPO//\//-}"
OUTDIR="$ROOT/review-mining/$SLUG"
mkdir -p "$OUTDIR"

echo "Phase 1: enumerating PRs for $REPO (limit $LIMIT) ..." >&2

gh pr list \
  --repo "$REPO" \
  --state all \
  --limit "$LIMIT" \
  --json number,title,state,author,createdAt,closedAt,mergedAt,baseRefName,headRefName,url \
  > "$OUTDIR/01-prs.json"

COUNT="$(jq 'length' "$OUTDIR/01-prs.json")"
# No silent caps: if we returned exactly the limit, there may be more PRs.
if [[ "$COUNT" -ge "$LIMIT" ]]; then
  echo "  WARN: hit the --limit ($LIMIT); repo may have more PRs. Re-run with a higher limit." >&2
fi
echo "Wrote $COUNT PRs to $OUTDIR/01-prs.json" >&2
echo "$OUTDIR/01-prs.json"
