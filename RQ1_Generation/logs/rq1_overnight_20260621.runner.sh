#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODELS=(gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview)
echo "[START] RQ1 overnight $(date)"
echo "[criteria] RQ1 uses bounded equivalence check in Example.ProcessNewResults: check { P <=> P2 } for 5. No AREPAIR_VALIDATION branch is used by rq1-process-english/rq1-process-alloy."
for model in "${MODELS[@]}"; do
  echo "=== RQ1 model=$model task=both ==="
  bash "RQ1_Generation/eval/run_rq1_eval.sh" "$model" both
  echo "=== done RQ1 model=$model ==="
done
echo "[END] RQ1 overnight $(date)"
