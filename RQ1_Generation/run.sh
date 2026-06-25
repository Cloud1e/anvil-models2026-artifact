#!/usr/bin/env bash
# Final RQ1 entrypoint: evaluate existing RQ1 model-generation outputs.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ARTIFACT_ROOT"

MODE="${1:---quick}"
MODEL="${MODEL:-gemini-3.1-flash-lite-preview}"
PROPERTY="${PROPERTY:-Function}"
QUICK_ROOT="logs/quick_start/RQ1/${MODEL}_${PROPERTY}"

usage() {
  cat <<'EOF'
Usage: bash RQ1_Generation/run.sh [--quick|--full]

  --quick  Evaluate one model/property for both English-to-Alloy and Alloy-to-Alloy.
  --full   Evaluate all three Gemini models for both tasks.

Optional quick env:
  MODEL=gemini-3.1-flash-lite-preview
  PROPERTY=Function
EOF
}

run_rq1_task() {
  local task="$1"
  local root="$2"
  mvn -q compile exec:java \
    -Dexec.mainClass=Example \
    -Dexec.args="rq1-process-${task} ${root}"
}

prepare_quick_root() {
  rm -rf "$QUICK_ROOT"
  mkdir -p \
    "$QUICK_ROOT/E2A/EnglishToAlloy/responses" \
    "$QUICK_ROOT/A2A/AlloyToAlloy/responses"
  cp \
    "RQ1_Generation/outputs/E2A/${MODEL}/EnglishToAlloy/responses/${PROPERTY}.txt" \
    "$QUICK_ROOT/E2A/EnglishToAlloy/responses/${PROPERTY}.txt"
  cp \
    "RQ1_Generation/outputs/A2A/${MODEL}/AlloyToAlloy/responses/${PROPERTY}.txt" \
    "$QUICK_ROOT/A2A/AlloyToAlloy/responses/${PROPERTY}.txt"
}

case "$MODE" in
  --quick)
    echo "RQ1 quick: model=${MODEL} property=${PROPERTY}"
    prepare_quick_root
    run_rq1_task english "$QUICK_ROOT/E2A"
    run_rq1_task alloy "$QUICK_ROOT/A2A"
    echo "RQ1 quick completed. Outputs under ${QUICK_ROOT}/{E2A,A2A}."
    ;;
  --full)
    echo "RQ1 full: all models, English-to-Alloy and Alloy-to-Alloy"
    for model in gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview; do
      echo "=== RQ1 full model=${model} ==="
      bash RQ1_Generation/eval/run_rq1_eval.sh "$model" both
    done
    echo "RQ1 full completed."
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
