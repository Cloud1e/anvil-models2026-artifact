#!/usr/bin/env bash
# Final RQ3 entrypoint: classify faulty models and optionally run ARepair.
# Classification primary source is fixed in classify_faulty_models.py:
# Example --check-one, with testsuite/predEquiv retained as diagnostics.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ARTIFACT_ROOT"

MODE="${1:---quick}"
MODEL="${MODEL:-gemini-3.1-flash-lite-preview}"
export TIMEOUT="${TIMEOUT:-600}"

usage() {
  cat <<'EOF'
Usage: bash RQ3_Repair/run.sh [--quick|--full]

  --quick  Classify one model only; does not run ARepair repair.
  --full   Classify and repair all three Gemini models.

RQ3 classification primary source is Example --check-one.

Optional quick env:
  MODEL=gemini-3.1-flash-lite-preview
EOF
}

run_model() {
  local model="$1"
  local repair_flag="$2"
  bash RQ3_Repair/run_faulty_rewrite_pipeline.sh \
    --model "$model" \
    --out-root "result/Gemini/RQ3_Repair/FaultyRewrite/${model}/ARepair_FaultyRewrite" \
    --skip-llm \
    "$repair_flag"
}

case "$MODE" in
  --quick)
    echo "RQ3 quick: model=${MODEL}; classification only"
    run_model "$MODEL" --skip-arepair
    echo "RQ3 quick completed."
    ;;
  --full)
    echo "RQ3 full: all models; classification + ARepair repair"
    for model in gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview; do
      echo "=== RQ3 full model=${model} ==="
      run_model "$model" --run-arepair
    done
    echo "RQ3 full completed."
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
