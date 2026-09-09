#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${ISSUE32_CANDIDATE:?set ISSUE32_CANDIDATE to A or B}"
: "${ISSUE32_WORKTREE:?set ISSUE32_WORKTREE to the candidate worktree}"
: "${ISSUE32_SOURCE_REF:?set ISSUE32_SOURCE_REF to the immutable candidate ref}"
: "${ISSUE32_EVIDENCE_DIR:?set ISSUE32_EVIDENCE_DIR to a new evidence directory}"

exec /usr/bin/python3 "$SCRIPT_DIR/issue32_apparatus.py" gate \
    --candidate "$ISSUE32_CANDIDATE" \
    --worktree "$ISSUE32_WORKTREE" \
    --source-ref "$ISSUE32_SOURCE_REF" \
    --output-dir "$ISSUE32_EVIDENCE_DIR" \
    --workload "${ISSUE32_WORKLOAD:-normal}" \
    --instrumentation "${ISSUE32_INSTRUMENTATION:-full}" \
    --run-ordinal "${ISSUE32_RUN_ORDINAL:-1}"
