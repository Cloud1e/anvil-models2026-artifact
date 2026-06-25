#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODELS=(gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview)
export AREPAIR_VALIDATION=testsuite
export TIMEOUT="${TIMEOUT:-600}"
echo "[START] RQ2 overnight $(date)"
echo "[criteria] RQ2 locked to AREPAIR_VALIDATION=testsuite."
for model in "${MODELS[@]}"; do
  echo "=== RQ2 E2A model=$model ==="
  flock "$ROOT/logs/arepair_overnight.lock" bash "RQ2_Validation/english_to_alloy/run_rq1_e2a_full_host.sh" "result/Gemini/RQ2_Validation/E2A/$model"
  echo "=== done RQ2 E2A model=$model ==="
  echo "=== RQ2 A2A model=$model ==="
  flock "$ROOT/logs/arepair_overnight.lock" bash "RQ2_Validation/alloy_to_alloy/run_rq1_a2a_full_host.sh" "result/Gemini/RQ2_Validation/A2A/$model"
  echo "=== done RQ2 A2A model=$model ==="
done
echo "[END] RQ2 overnight $(date)"
