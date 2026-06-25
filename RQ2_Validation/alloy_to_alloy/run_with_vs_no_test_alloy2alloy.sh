#!/bin/bash
# Alloy-to-Alloy full flow: evaluate, compare, extract Wrong, run ARepair.
# Supports model-specific out-root under result/Gemini/RQ2_Validation/A2A/<model>.

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
cd "$PROJECT_DIR"
# shellcheck disable=SC1091
source "$ARTIFACT_ROOT/lib/docker_paths.sh"
THESIS_RQ1="$ARTIFACT_ROOT/RQ2_Validation"

if [ "$1" != "--in-docker" ]; then
  PYTHON_BIN="${PYTHON_BIN:-python}"
  MODEL=""
  OUT_ROOT=""
  BENCH_MODELS=""
  GEN=0
  SKIP_REPAIR=0

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --model)
        MODEL="$2"
        shift 2
        ;;
      --out-root)
        OUT_ROOT="$2"
        shift 2
        ;;
      --bench-models)
        BENCH_MODELS="$2"
        shift 2
        ;;
      --gen)
        GEN=1
        shift 1
        ;;
      --no-repair)
        SKIP_REPAIR=1
        shift 1
        ;;
      *)
        echo "Unknown argument: $1" >&2
        echo "Usage: bash .../run_with_vs_no_test_alloy2alloy.sh [--model ...] [--out-root ...] [--bench-models student,cd,...] [--gen] [--no-repair]" >&2
        exit 1
        ;;
    esac
  done

  if [ "$GEN" -eq 1 ]; then
    if [ -z "$MODEL" ] || [ -z "$OUT_ROOT" ] || [ -z "$BENCH_MODELS" ]; then
      echo "Error: --gen requires --model, --out-root, and --bench-models" >&2
      exit 1
    fi
    IFS=',' read -r -a MODELS_ARR <<< "$BENCH_MODELS"
    mkdir -p "$OUT_ROOT/WithTest/responses" "$OUT_ROOT/NoTest/responses"
    for m in "${MODELS_ARR[@]}"; do
      m="$(echo "$m" | xargs)"
      [ -z "$m" ] && continue
      WT_IN="query/Gemini/ARepair_Alloy2Alloy_WithTest/$m"
      NT_IN="query/Gemini/ARepair_Alloy2Alloy_NoTest/$m"
      WT_OUT="$OUT_ROOT/WithTest/responses/$m.txt"
      NT_OUT="$OUT_ROOT/NoTest/responses/$m.txt"
      echo "=== [GEN] $m (WithTest) ==="
      "$PYTHON_BIN" "$THESIS_RQ1/english_to_alloy/run_gemini_etoa_single.py" \
        --model "$MODEL" --input "$WT_IN" --output "$WT_OUT"
      echo ""
      echo "=== [GEN] $m (NoTest) ==="
      "$PYTHON_BIN" "$THESIS_RQ1/english_to_alloy/run_gemini_etoa_single.py" \
        --model "$MODEL" --input "$NT_IN" --output "$NT_OUT"
      echo ""
    done
  fi

  mkdir -p "$PROJECT_DIR/logs"
  if [ -n "$MODEL" ]; then
    MODEL_SLUG=$(echo "$MODEL" | tr '/:' '__')
    LOG_NAME="with_vs_no_test_alloy2alloy_${MODEL_SLUG}_$(date +%Y%m%d_%H%M%S).log"
  else
    LOG_NAME="with_vs_no_test_alloy2alloy_$(date +%Y%m%d_%H%M%S).log"
  fi
  LOG_PATH="$PROJECT_DIR/logs/$LOG_NAME"
  COMPOSE_FILE="$PROJECT_DIR/docker-compose.arepair.yml"
  if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Error: docker-compose.arepair.yml not found."
    exit 1
  fi
  EXTRA_ARGS=""
  [ -n "$MODEL" ] && EXTRA_ARGS="$EXTRA_ARGS --model \"$MODEL\""
  [ -n "$OUT_ROOT" ] && EXTRA_ARGS="$EXTRA_ARGS --out-root \"$OUT_ROOT\""
  [ -n "$BENCH_MODELS" ] && EXTRA_ARGS="$EXTRA_ARGS --bench-models \"$BENCH_MODELS\""
  [ "$SKIP_REPAIR" -eq 1 ] && EXTRA_ARGS="$EXTRA_ARGS --no-repair"
  echo "Running Alloy-to-Alloy full flow in Docker. Log: $LOG_PATH"
  docker-compose -f "$COMPOSE_FILE" run --rm -e "A2A_LOG=logs/$LOG_NAME" arepair bash -c \
    "set -o pipefail; cd /workspace && bash RQ2_Validation/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh --in-docker $EXTRA_ARGS 2>&1 | tee /workspace/logs/$LOG_NAME"
  echo "Done. Full log: $LOG_PATH"
  exit 0
fi

# --- In docker ---
shift
MODEL=""
OUT_ROOT=""
BENCH_MODELS=""
SKIP_REPAIR=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL="$2"
      shift 2
      ;;
    --out-root)
      OUT_ROOT="$2"
      shift 2
      ;;
    --bench-models)
      BENCH_MODELS="$2"
      shift 2
      ;;
    --no-repair)
      SKIP_REPAIR=1
      shift 1
      ;;
    *)
      echo "Unknown argument (in-docker): $1" >&2
      exit 1
      ;;
  esac
done
# shellcheck disable=SC1091
source /workspace/lib/docker_paths.sh
docker_normalize_repo_rel OUT_ROOT || exit 1
if [ -n "$BENCH_MODELS" ]; then
  export AREPAIR_BENCH_MODELS="$BENCH_MODELS"
  echo "[filter] AREPAIR_BENCH_MODELS=$AREPAIR_BENCH_MODELS"
fi

cd /workspace
mkdir -p logs

EXTRACT_FILTER=()
COMPARE_FILTER=()
if [ -n "$BENCH_MODELS" ]; then
  EXTRACT_FILTER=(--bench-models "$BENCH_MODELS")
  COMPARE_FILTER=(--bench-models "$BENCH_MODELS")
fi

cleanup_links() {
  rm -f /workspace/result/Gemini/ARepair_Alloy2Alloy_WithTest /workspace/result/Gemini/ARepair_Alloy2Alloy_NoTest
}
if [ -n "$OUT_ROOT" ]; then
  mkdir -p "/workspace/$OUT_ROOT/WithTest" "/workspace/$OUT_ROOT/NoTest"
  cleanup_links
  ln -s "/workspace/$OUT_ROOT/WithTest" /workspace/result/Gemini/ARepair_Alloy2Alloy_WithTest
  ln -s "/workspace/$OUT_ROOT/NoTest" /workspace/result/Gemini/ARepair_Alloy2Alloy_NoTest
  trap cleanup_links EXIT
  echo "[path] Using out-root: $OUT_ROOT"
  echo "[path] Legacy ARepair_Alloy2Alloy_WithTest -> $OUT_ROOT/WithTest"
  echo "[path] Legacy ARepair_Alloy2Alloy_NoTest -> $OUT_ROOT/NoTest"
  echo ""
fi

# Filter noisy Java/Kodkod output
EVAL_FILTER='^(=== Debug for|Predicates to repair: \[|Other predicates \(not repaired\)|Response line:|Extracted predName:|Extracted predBody:|Predicate signature |Predicate section in test|Other predicates string length|SLF4J:|[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]+.*INFO  kodkod|DEBUG: |Command for first test|Test test[0-9]+: expected|^Solutions$|^false$|^SAME_CODE$|^Correct$|^Wrong$|^Syntax Error$|Detailed test report written to)'
EVAL_LOG=$(mktemp)
trap "rm -f '$EVAL_LOG'" EXIT

echo "=== Alloy-to-Alloy: Evaluate WithTest + NoTest (Java) ==="
set +e
python3 RQ2_Validation/alloy_to_alloy/evaluate_alloy2alloy_responses.py > "$EVAL_LOG" 2>&1
EVAL_EC=$?
set -e
grep -v -E "$EVAL_FILTER" "$EVAL_LOG" || true
[ "$EVAL_EC" -ne 0 ] && exit "$EVAL_EC"

COMPARE_COR_ONLY=()
if [ "${SKIP_REPAIR:-0}" -eq 1 ]; then
  COMPARE_COR_ONLY=(--cor-syn-sem-only)
fi

echo ""
echo "=== Alloy-to-Alloy: Compare WithTest vs NoTest (Cor/Syn/Sem) ==="
python3 RQ2_Validation/alloy_to_alloy/compare_with_vs_without_test_alloy2alloy.py --no-tex "${COMPARE_COR_ONLY[@]}" "${COMPARE_FILTER[@]}"

if [ "${SKIP_REPAIR:-0}" -eq 0 ]; then
  echo ""
  echo "=== Alloy-to-Alloy: Build ARepair once in Docker ==="
  cd /workspace/ARepair && ./arepair.sh --build && cd /workspace

  echo ""
  echo "=== Alloy-to-Alloy: Extract Wrong for WithTest and run ARepair ==="
  python3 scripts/arepair/extract_wrong_predicates.py "${EXTRACT_FILTER[@]}" \
    --alloy-dir result/Gemini/ARepair_Alloy2Alloy_WithTest/Alloy \
    --output-dir result/Gemini/ARepair_Alloy2Alloy_WithTest/WrongForRepair
  REPAIR_INFO_WITH="result/Gemini/ARepair_Alloy2Alloy_WithTest/WrongForRepair/repair_info.json"
  REPAIR_OUT_WITH="result/Gemini/ARepair_Alloy2Alloy_WithTest/RepairResults"
  if [ -f "$REPAIR_INFO_WITH" ] && [ -s "$REPAIR_INFO_WITH" ]; then
    export REPAIR_INFO_JSON="/workspace/$REPAIR_INFO_WITH"
    export OUTPUT_DIR="/workspace/$REPAIR_OUT_WITH"
    python3 scripts/arepair/run_arepair.py
  else
    echo "No WithTest Wrong to repair."
  fi

  echo ""
  echo "=== Alloy-to-Alloy: Extract Wrong for NoTest and run ARepair ==="
  python3 scripts/arepair/extract_wrong_predicates.py "${EXTRACT_FILTER[@]}" \
    --alloy-dir result/Gemini/ARepair_Alloy2Alloy_NoTest/Alloy \
    --output-dir result/Gemini/ARepair_Alloy2Alloy_NoTest/WrongForRepair
  REPAIR_INFO_NO="result/Gemini/ARepair_Alloy2Alloy_NoTest/WrongForRepair/repair_info.json"
  REPAIR_OUT_NO="result/Gemini/ARepair_Alloy2Alloy_NoTest/RepairResults"
  if [ -f "$REPAIR_INFO_NO" ] && [ -s "$REPAIR_INFO_NO" ]; then
    export REPAIR_INFO_JSON="/workspace/$REPAIR_INFO_NO"
    export OUTPUT_DIR="/workspace/$REPAIR_OUT_NO"
    python3 scripts/arepair/run_arepair.py
  else
    echo "No NoTest Wrong to repair."
  fi
else
  echo ""
  echo "=== ARepair steps skipped (--no-repair) ==="
fi

echo ""
echo "=== Alloy-to-Alloy: Compare (write LaTeX; Rep only after repair) ==="
COMPARE_TEX_EXTRA=()
TEX_SUFFIX=""
if [ -n "$MODEL" ]; then
  TEX_SUFFIX="$MODEL"
elif [ -n "$OUT_ROOT" ]; then
  TEX_SUFFIX="$(basename "$OUT_ROOT")"
fi
if [ -n "$TEX_SUFFIX" ]; then
  COMPARE_TEX_EXTRA=(--tex-suffix "$TEX_SUFFIX")
  echo "[tex] Writing per-run file: result/with_vs_no_test_alloy2alloy_by_predicate_${TEX_SUFFIX}.tex"
fi
python3 RQ2_Validation/alloy_to_alloy/compare_with_vs_without_test_alloy2alloy.py "${COMPARE_TEX_EXTRA[@]}" "${COMPARE_COR_ONLY[@]}" "${COMPARE_FILTER[@]}"

echo ""
if [ -n "$TEX_SUFFIX" ]; then
  echo "Done. LaTeX table: result/with_vs_no_test_alloy2alloy_by_predicate_${TEX_SUFFIX}.tex"
else
  echo "Done. LaTeX table: result/with_vs_no_test_alloy2alloy_by_predicate.tex"
fi
if [ -n "${A2A_LOG:-}" ]; then
  echo "Full log: $A2A_LOG"
fi
