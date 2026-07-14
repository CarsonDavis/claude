#!/usr/bin/env bash
#
# Phase 3 prep — flatten all per-PR thread files into one record-per-file layout
# that the verdict workflow fans out over.
#
# Usage:  split-threads.sh <owner/repo>
# Output: review-mining/<owner-repo>/03-all-threads.json   (flat array, audit copy)
#         review-mining/<owner-repo>/03-input/rec-NNNNN.json  (one thread each)
# Prints: the record COUNT on stdout (the workflow needs it).
#
# One jq pass + one awk pass, so it scales to thousands of threads without
# spawning a process per record. Index width is fixed at 5 digits to match the
# zero-padding in phase3-verdict.workflow.js.

set -euo pipefail

REPO="${1:?usage: split-threads.sh <owner/repo>}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
SLUG="${REPO//\//-}"
OUTDIR="$ROOT/review-mining/$SLUG"
THREADDIR="$OUTDIR/02-threads"
INDIR="$OUTDIR/03-input"

[[ -d "$THREADDIR" ]] || { echo "no 02-threads/ dir at $THREADDIR — run phase 2 first" >&2; exit 1; }

jq -s 'add // []' "$THREADDIR"/PR-*.json > "$OUTDIR/03-all-threads.json"
COUNT="$(jq 'length' "$OUTDIR/03-all-threads.json")"

rm -rf "$INDIR"; mkdir -p "$INDIR"
# Write each record (one compact JSON line) to its own zero-padded file.
jq -c '.[]' "$OUTDIR/03-all-threads.json" \
  | awk -v dir="$INDIR" '{ fn=sprintf("%s/rec-%05d.json", dir, NR-1); print > fn; close(fn) }'

echo "Split $COUNT thread records into $INDIR/rec-NNNNN.json" >&2
echo "$COUNT"
