#!/usr/bin/env bash
# Final RQ2 entrypoint: validate English-to-Alloy and Alloy-to-Alloy outputs.
# The validation criterion is intentionally fixed to test-suite validation.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ARTIFACT_ROOT"

MODE="${1:---quick}"
MODEL="${MODEL:-gemini-3.1-flash-lite-preview}"
BENCH="${BENCH:-arr}"
export AREPAIR_VALIDATION=testsuite
export TIMEOUT="${TIMEOUT:-600}"

compose_cmd() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

usage() {
  cat <<'EOF'
Usage: bash RQ2_Validation/run.sh [--quick|--full]

  --quick  Re-evaluate one benchmark for one model without ARepair repair.
  --full   Reproduce all RQ2 E2A and A2A tables with ARepair repair.

RQ2 always uses AREPAIR_VALIDATION=testsuite.

Optional quick env:
  MODEL=gemini-3.1-flash-lite-preview
  BENCH=arr
EOF
}

run_e2a() {
  local model="$1"
  local out_root="$2"
  env AREPAIR_VALIDATION=testsuite TIMEOUT="$TIMEOUT" \
    bash RQ2_Validation/english_to_alloy/run_rq1_e2a_full_host.sh "$out_root"
}

run_a2a() {
  local model="$1"
  local out_root="$2"
  compose_cmd -f docker-compose.arepair.yml run --rm arepair bash -lc \
    "set -e; cd /workspace; export AREPAIR_VALIDATION=testsuite TIMEOUT=${TIMEOUT}; bash RQ2_Validation/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh --in-docker --model '${model}' --out-root '${out_root}'"
}

case "$MODE" in
  --quick)
    echo "RQ2 quick: model=${MODEL} benchmark=${BENCH}"
    export THESIS_SMOKE_BENCH="$BENCH"
    export SKIP_REPAIR=1
    run_e2a "$MODEL" "result/Gemini/RQ2_Validation/E2A/${MODEL}"
    compose_cmd -f docker-compose.arepair.yml run --rm arepair bash -lc \
      "set -e; cd /workspace; export AREPAIR_VALIDATION=testsuite TIMEOUT=${TIMEOUT}; bash RQ2_Validation/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh --in-docker --model '${MODEL}' --out-root 'result/Gemini/RQ2_Validation/A2A/${MODEL}' --bench-models '${BENCH}' --no-repair"
    echo "RQ2 quick completed."
    ;;
  --full)
    echo "RQ2 full: all models, test-suite validation"
    unset THESIS_SMOKE_BENCH
    unset SKIP_REPAIR
    for model in gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview; do
      echo "=== RQ2 full E2A model=${model} ==="
      run_e2a "$model" "result/Gemini/RQ2_Validation/E2A/${model}"
      echo "=== RQ2 full A2A model=${model} ==="
      run_a2a "$model" "result/Gemini/RQ2_Validation/A2A/${model}"
    done
    echo "RQ2 full completed."
    ;;
  -h|--help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
