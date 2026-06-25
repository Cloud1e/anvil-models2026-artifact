#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODELS=(gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview)
export TIMEOUT="${TIMEOUT:-600}"
echo "[START] RQ3 overnight $(date)"
echo "[criteria] RQ3 classification uses Rq3ParallelTestSuiteOracle testsuite_oracle; ARepair runs on repair_info_original and repair_info_llm."
for model in "${MODELS[@]}"; do
  echo "=== RQ3 classify + ARepair model=$model ==="
  flock "$ROOT/logs/arepair_overnight.lock" bash "RQ3_Repair/run_faulty_rewrite_pipeline.sh" \
    --model "$model" \
    --out-root "result/Gemini/RQ3_Repair/FaultyRewrite/$model/ARepair_FaultyRewrite" \
    --skip-llm \
    --run-arepair
  echo "=== done RQ3 model=$model ==="
done
echo "[END] RQ3 overnight $(date)"
