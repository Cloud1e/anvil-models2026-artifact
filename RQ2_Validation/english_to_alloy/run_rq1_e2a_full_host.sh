#!/usr/bin/env bash
# RQ1 E2A: re-evaluate existing responses, extract Wrong, run ARepair, write thesis table.
# All output goes directly under result/thesis/RQ1_TestVsNoTest/E2A/<model>/ — no symlinks.
#
# Usage (from repo root):
#   bash scripts/thesis/RQ1_TestVsNoTest/english_to_alloy/run_rq1_e2a_full_host.sh \
#     result/thesis/RQ1_TestVsNoTest/E2A/gemini-3-flash-preview
#
# Env:
#   SKIP_REPAIR=1   — skip ARepair (Steps 4–5), only Cor/Syn/Sem
#   TIMEOUT         — per-predicate ARepair seconds (default: 600)
#   AREPAIR_VALIDATION — default testsuite (unified thesis); set equivalence for bounded check only
#   THESIS_LOG_FILE — if set, tee all output here (mkdir -p dirname); else use logs/rq1_e2a_<slug>_<ts>.log
#   THESIS_SMOKE_BENCH — optional single benchmark (e.g. arr): AREPAIR_BENCH_MODELS, extract_wrong --bench-models, REPAIR_FILTER for ARepair.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPO_ROOT="$ARTIFACT_ROOT"
cd "$REPO_ROOT"
# shellcheck disable=SC1091
source "$ARTIFACT_ROOT/lib/docker_paths.sh"

OUT_ROOT="${1:-result/thesis/RQ1_TestVsNoTest/E2A/gemini-3.1-flash-lite-preview}"
WITH_DIR="$OUT_ROOT/WithTest"
NO_DIR="$OUT_ROOT/NoTest"

if [[ ! -d "$WITH_DIR/responses" || ! -d "$NO_DIR/responses" ]]; then
  echo "ERROR: missing responses under $OUT_ROOT/{WithTest,NoTest}/responses" >&2
  exit 1
fi

EVAL_DIR="$ARTIFACT_ROOT/RQ2_Validation/english_to_alloy"
TEX_SLUG="$(basename "$OUT_ROOT")"
export TIMEOUT="${TIMEOUT:-600}"
export AREPAIR_VALIDATION="${AREPAIR_VALIDATION:-testsuite}"

EXTRACT_EXTRA=()
COMPARE_BENCH=()
if [[ -n "${THESIS_SMOKE_BENCH:-}" ]]; then
  export AREPAIR_BENCH_MODELS="$THESIS_SMOKE_BENCH"
  EXTRACT_EXTRA=(--bench-models "$THESIS_SMOKE_BENCH")
  COMPARE_BENCH=(--bench-models "$THESIS_SMOKE_BENCH")
  echo "[smoke] AREPAIR_BENCH_MODELS=$AREPAIR_BENCH_MODELS (extract_wrong + ARepair --filter; compare table rows only)"
fi

if [[ -n "${THESIS_LOG_FILE:-}" ]]; then
  LOG_FILE="$THESIS_LOG_FILE"
else
  mkdir -p logs
  LOG_FILE="logs/rq1_e2a_${TEX_SLUG}_$(date +%Y%m%d_%H%M%S).log"
fi
mkdir -p "$(dirname "$LOG_FILE")"
exec > >(tee -a "$LOG_FILE") 2>&1
echo "Log: $LOG_FILE"

echo "============================================================"
echo "RQ1 E2A: $TEX_SLUG"
echo "  WithTest: $WITH_DIR"
echo "  NoTest:   $NO_DIR"
echo "============================================================"

echo ""
echo "=== Step 1: Java eval (NoTest then WithTest) ==="
python3 "$EVAL_DIR/evaluate_notest_responses.py"  --result-dir "$NO_DIR"
python3 "$EVAL_DIR/evaluate_withtest_responses.py" --result-dir "$WITH_DIR"

echo ""
echo "=== Step 2: Compare (Cor/Syn/Sem; preliminary) ==="
python3 "$EVAL_DIR/compare_with_vs_without_test.py" \
  --with-alloy-dir "$WITH_DIR/Alloy" \
  --no-alloy-dir "$NO_DIR/Alloy" \
  --tex-suffix "$TEX_SLUG" --cor-syn-sem-only \
  "${COMPARE_BENCH[@]}"

echo ""
echo "=== Step 3: extract_wrong (NoTest then WithTest) ==="
python3 "$ARTIFACT_ROOT/scripts/arepair/extract_wrong_predicates.py" "${EXTRACT_EXTRA[@]}" \
  --alloy-dir "$NO_DIR/Alloy" \
  --output-dir "$NO_DIR/WrongForRepair"
python3 "$ARTIFACT_ROOT/scripts/arepair/extract_wrong_predicates.py" "${EXTRACT_EXTRA[@]}" \
  --alloy-dir "$WITH_DIR/Alloy" \
  --output-dir "$WITH_DIR/WrongForRepair"

if [[ "${SKIP_REPAIR:-0}" == "1" ]]; then
  echo ""
  echo "SKIP_REPAIR=1 — done (no ARepair)."
  echo "LaTeX: result/thesis/RQ1_TestVsNoTest/tables/with_vs_no_test_by_predicate_${TEX_SLUG}.tex"
  exit 0
fi

COMPOSE_FILE="$REPO_ROOT/docker-compose.arepair.yml"
if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "ERROR: docker-compose.arepair.yml not found." >&2
  exit 1
fi

echo ""
echo "=== Step 4: ARepair in Docker (NoTest) ==="
NO_REPAIR_INFO="$NO_DIR/WrongForRepair/repair_info.json"
NO_REPAIR_OUT="$NO_DIR/RepairResults"
if [[ -f "$NO_REPAIR_INFO" ]] && [[ -s "$NO_REPAIR_INFO" ]]; then
  mkdir -p "$NO_REPAIR_OUT"
  WS_NO_REPAIR_INFO="$(host_to_workspace "$REPO_ROOT" "$NO_REPAIR_INFO")"
  WS_NO_REPAIR_OUT="$(host_to_workspace "$REPO_ROOT" "$NO_REPAIR_OUT")"
  DOCKER_EXTRA_E2A=()
  [[ -n "${THESIS_SMOKE_BENCH:-}" ]] && DOCKER_EXTRA_E2A+=(-e "REPAIR_FILTER=$THESIS_SMOKE_BENCH")
  docker-compose -f "$COMPOSE_FILE" run --rm \
    -e "REPAIR_INFO_JSON=$WS_NO_REPAIR_INFO" \
    -e "OUTPUT_DIR=$WS_NO_REPAIR_OUT" \
    -e "TIMEOUT=$TIMEOUT" \
    "${DOCKER_EXTRA_E2A[@]}" \
    arepair bash -c \
    "cd /workspace/ARepair && ./arepair.sh --build && cd /workspace && python3 -u scripts/arepair/run_arepair.py"
else
  echo "No NoTest repair_info.json — skip."
fi

echo ""
echo "=== Step 5: ARepair in Docker (WithTest) ==="
WITH_REPAIR_INFO="$WITH_DIR/WrongForRepair/repair_info.json"
WITH_REPAIR_OUT="$WITH_DIR/RepairResults"
if [[ -f "$WITH_REPAIR_INFO" ]] && [[ -s "$WITH_REPAIR_INFO" ]]; then
  mkdir -p "$WITH_REPAIR_OUT"
  WS_WITH_REPAIR_INFO="$(host_to_workspace "$REPO_ROOT" "$WITH_REPAIR_INFO")"
  WS_WITH_REPAIR_OUT="$(host_to_workspace "$REPO_ROOT" "$WITH_REPAIR_OUT")"
  DOCKER_EXTRA_E2A_W=()
  [[ -n "${THESIS_SMOKE_BENCH:-}" ]] && DOCKER_EXTRA_E2A_W+=(-e "REPAIR_FILTER=$THESIS_SMOKE_BENCH")
  docker-compose -f "$COMPOSE_FILE" run --rm \
    -e "REPAIR_INFO_JSON=$WS_WITH_REPAIR_INFO" \
    -e "OUTPUT_DIR=$WS_WITH_REPAIR_OUT" \
    -e "TIMEOUT=$TIMEOUT" \
    "${DOCKER_EXTRA_E2A_W[@]}" \
    arepair bash -c \
    "cd /workspace/ARepair && ./arepair.sh --build && cd /workspace && python3 -u scripts/arepair/run_arepair.py"
else
  echo "No WithTest repair_info.json — skip."
fi

echo ""
echo "=== Step 6: Final table (with Rep columns) ==="
python3 "$EVAL_DIR/compare_with_vs_without_test.py" \
  --with-alloy-dir "$WITH_DIR/Alloy" \
  --no-alloy-dir "$NO_DIR/Alloy" \
  --repair-with "$WITH_DIR/RepairResults/repair_results.json" \
  --repair-no "$NO_DIR/RepairResults/repair_results.json" \
  --tex-suffix "$TEX_SLUG" \
  "${COMPARE_BENCH[@]}"
echo "Done. LaTeX: result/thesis/RQ1_TestVsNoTest/tables/with_vs_no_test_by_predicate_${TEX_SLUG}.tex"
