#!/bin/bash
# Single script: full flow (evaluate WithTest+NoTest, compare, ARepair both, stats).
# Run from host (project root); script starts Docker and runs everything inside the container.
# Output is teed to logs/with_vs_no_test_YYYYMMDD_HHMMSS.log.
#
# Usage (from project root, no need to run docker yourself):
#   bash scripts/with_vs_without_test/english_to_alloy/run_with_vs_no_test.sh
#   bash scripts/with_vs_without_test/english_to_alloy/run_with_vs_no_test.sh --notest-repair-only   # skip WithTest ARepair, only run NoTest ARepair (use existing WithTest repair data)
#   bash scripts/with_vs_without_test/english_to_alloy/run_with_vs_no_test.sh --model gemini-3-flash-preview --out-root result/Gemini/RQ2_Validation/E2A/gemini-3-flash-preview --bench-models arr
#   bash scripts/with_vs_without_test/english_to_alloy/run_with_vs_no_test.sh --model gemini-3-flash-preview --out-root result/Gemini/RQ2_Validation/E2A/gemini-3-flash-preview --bench-models arr --gen
#
#   --bench-models student,cd,... (optional): evaluate + extract_wrong + repair only for those benchmarks
#     (basename without .txt). Sets AREPAIR_BENCH_MODELS in the container; Java uses -Darepair.bench.models=...
#   --no-repair: only Java eval + Cor/Syn/Sem compare (and LaTeX without Rep columns). Skips ARepair.
#
# Prerequisites:
#   - If NOT using --out-root:
#       - WithTest: result/Gemini/ARepair/responses/ + result/Gemini/ARepair/Alloy/
#       - NoTest:   result/Gemini/ARepairNoTest/responses/ (LLM outputs)
#   - If using --out-root (recommended for RQ2):
#       - WithTest: <out-root>/WithTest/responses/
#       - NoTest:   <out-root>/NoTest/responses/
#   - Docker + docker-compose; ARepair built in image

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
cd "$PROJECT_DIR"
# shellcheck disable=SC1091
source "$ARTIFACT_ROOT/lib/docker_paths.sh"
THESIS_RQ1="$ARTIFACT_ROOT/RQ2_Validation"

# If not running inside Docker, start container and run this script with --in-docker
if [ "$1" != "--in-docker" ]; then
  PYTHON_BIN="${PYTHON_BIN:-python}"
  MODEL=""
  OUT_ROOT=""
  BENCH_MODELS=""
  GEN=0
  NOTEST_REPAIR_ONLY=0
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
        BENCH_MODELS="$2" # comma-separated, e.g., "arr,cd"
        shift 2
        ;;
      --gen)
        GEN=1
        shift 1
        ;;
      --notest-repair-only)
        NOTEST_REPAIR_ONLY=1
        shift 1
        ;;
      --no-repair)
        SKIP_REPAIR=1
        shift 1
        ;;
      *)
        echo "Unknown argument: $1" >&2
        echo "Usage: bash scripts/with_vs_without_test/english_to_alloy/run_with_vs_no_test.sh [--model ...] [--out-root ...] [--bench-models ...] [--gen] [--notest-repair-only] [--no-repair]" >&2
        exit 1
        ;;
    esac
  done

  # Optional host-side generation (writes responses under OUT_ROOT/{WithTest,NoTest}/responses)
  if [ "$GEN" -eq 1 ]; then
    if [ -z "$MODEL" ] || [ -z "$OUT_ROOT" ] || [ -z "$BENCH_MODELS" ]; then
      echo "Error: --gen requires --model, --out-root, and --bench-models" >&2
      exit 1
    fi
    IFS=',' read -r -a MODELS_ARR <<< "$BENCH_MODELS"
    mkdir -p "$OUT_ROOT/WithTest/responses" "$OUT_ROOT/NoTest/responses"
    for m in "${MODELS_ARR[@]}"; do
      m="$(echo "$m" | xargs)" # trim
      if [ -z "$m" ]; then
        continue
      fi
      WT_IN="query/Gemini/ARepair/$m"
      NT_IN="query/Gemini/ARepairNoTest/$m"
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
  # Log filename includes model id (safe for filenames) so runs are easy to tell apart.
  if [ -n "$MODEL" ]; then
    MODEL_SLUG=$(echo "$MODEL" | tr '/:' '__')
    LOG_NAME="with_vs_no_test_${MODEL_SLUG}_$(date +%Y%m%d_%H%M%S).log"
  else
    LOG_NAME="with_vs_no_test_$(date +%Y%m%d_%H%M%S).log"
  fi
  LOG_PATH="$PROJECT_DIR/logs/$LOG_NAME"
  COMPOSE_FILE="$PROJECT_DIR/docker-compose.arepair.yml"
  if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Error: docker-compose.arepair.yml not found."
    exit 1
  fi
  REL_OUT_ROOT=""
  if [ -n "$OUT_ROOT" ]; then
    REL_OUT_ROOT="$(repo_relpath "$PROJECT_DIR" "$OUT_ROOT")"
  fi
  EXTRA_ARGS=""
  [ -n "$MODEL" ] && EXTRA_ARGS="$EXTRA_ARGS --model \"$MODEL\""
  [ -n "$OUT_ROOT" ] && EXTRA_ARGS="$EXTRA_ARGS --out-root \"$REL_OUT_ROOT\""
  [ -n "$BENCH_MODELS" ] && EXTRA_ARGS="$EXTRA_ARGS --bench-models \"$BENCH_MODELS\""
  [ "$NOTEST_REPAIR_ONLY" -eq 1 ] && EXTRA_ARGS="$EXTRA_ARGS --notest-repair-only"
  [ "${SKIP_REPAIR:-0}" -eq 1 ] && EXTRA_ARGS="$EXTRA_ARGS --no-repair"

  echo "Running full flow in Docker. Log: $LOG_PATH"
  docker-compose -f "$COMPOSE_FILE" run --rm -e "WITH_VS_NO_TEST_LOG=logs/$LOG_NAME" arepair bash -c \
    "cd /workspace && bash RQ2_Validation/english_to_alloy/run_with_vs_no_test.sh --in-docker $EXTRA_ARGS 2>&1 | tee /workspace/logs/$LOG_NAME"
  echo "Done. Full log: $LOG_PATH"
  exit 0
fi

# --- From here we are inside Docker (--in-docker) ---
shift
MODEL=""
OUT_ROOT=""
BENCH_MODELS=""
NOTEST_REPAIR_ONLY=0
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
    --notest-repair-only)
      NOTEST_REPAIR_ONLY=1
      shift 1
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
LOG_FILE="/workspace/${WITH_VS_NO_TEST_LOG:-logs/with_vs_no_test.log}"
echo "Log file: $LOG_FILE"
echo ""

# If OUT_ROOT is set, map legacy locations to OUT_ROOT via temporary symlinks.
# This lets us keep Example.java + existing Python scripts unchanged while storing
# artifacts under result/Gemini/RQ2_Validation/E2A/<model>/...
cleanup_links() {
  rm -f /workspace/result/Gemini/ARepair /workspace/result/Gemini/ARepairNoTest
}
if [ -n "$OUT_ROOT" ]; then
  mkdir -p "/workspace/$OUT_ROOT/WithTest" "/workspace/$OUT_ROOT/NoTest"
  cleanup_links
  ln -s "/workspace/$OUT_ROOT/WithTest" /workspace/result/Gemini/ARepair
  ln -s "/workspace/$OUT_ROOT/NoTest" /workspace/result/Gemini/ARepairNoTest
  trap cleanup_links EXIT
  echo "[path] Using out-root: $OUT_ROOT"
  echo "[path] Legacy ARepair -> $OUT_ROOT/WithTest"
  echo "[path] Legacy ARepairNoTest -> $OUT_ROOT/NoTest"
  echo ""
fi

# Step 1: Evaluate NoTest first, then WithTest (fresh Cor/Syn/Sem for both)
echo "=== Step 1: Evaluate NoTest then WithTest (fresh Alloy results) ==="
EXTRACT_FILTER=()
if [ -n "$BENCH_MODELS" ]; then
  EXTRACT_FILTER=(--bench-models "$BENCH_MODELS")
fi
python3 RQ2_Validation/english_to_alloy/evaluate_notest_responses.py
python3 RQ2_Validation/english_to_alloy/evaluate_withtest_responses.py

COMPARE_COR_ONLY=()
if [ "${SKIP_REPAIR:-0}" -eq 1 ]; then
  COMPARE_COR_ONLY=(--cor-syn-sem-only)
fi

echo ""
echo "=== Step 2: Compare WithTest vs NoTest (Cor/Syn/Sem by model-pred) ==="
python3 RQ2_Validation/english_to_alloy/compare_with_vs_without_test.py --no-tex "${COMPARE_COR_ONLY[@]}"

if [ "${SKIP_REPAIR:-0}" -eq 1 ]; then
  echo ""
  echo "=== Step 3–4: Skipped (--no-repair: no extract_wrong / ARepair) ==="
else
  echo ""
  echo "=== Step 3: Extract Wrong for NoTest and run ARepair ==="
  python3 scripts/arepair/extract_wrong_predicates.py "${EXTRACT_FILTER[@]}" \
    --alloy-dir result/Gemini/ARepairNoTest/Alloy \
    --output-dir result/Gemini/ARepairNoTest/WrongForRepair
  REPAIR_INFO_NO="/workspace/result/Gemini/ARepairNoTest/WrongForRepair/repair_info.json"
  REPAIR_OUT_NO="/workspace/result/Gemini/ARepairNoTest/RepairResults"
  if [ -f "$REPAIR_INFO_NO" ] && [ -s "$REPAIR_INFO_NO" ]; then
    export REPAIR_INFO_JSON="$REPAIR_INFO_NO"
    export OUTPUT_DIR="$REPAIR_OUT_NO"
    python3 scripts/arepair/run_arepair.py
  else
    echo "No NoTest Wrong to repair."
  fi

  if [ "$NOTEST_REPAIR_ONLY" -eq 0 ]; then
    echo ""
    echo "=== Step 4: Extract Wrong for WithTest and run ARepair ==="
    python3 scripts/arepair/extract_wrong_predicates.py "${EXTRACT_FILTER[@]}"
    REPAIR_INFO_WITH="/workspace/result/Gemini/ARepair/WrongForRepair/repair_info.json"
    REPAIR_OUT_WITH="/workspace/result/Gemini/ARepair/RepairResults"
    if [ -f "$REPAIR_INFO_WITH" ] && [ -s "$REPAIR_INFO_WITH" ]; then
      export REPAIR_INFO_JSON="$REPAIR_INFO_WITH"
      export OUTPUT_DIR="$REPAIR_OUT_WITH"
      python3 scripts/arepair/run_arepair.py
    else
      echo "No WithTest Wrong to repair."
    fi
  else
    echo ""
    echo "=== Step 4: Skipped (--notest-repair-only: use existing WithTest repair data) ==="
  fi
fi

echo ""
echo "=== Step 5: Compare (model-pred + LaTeX; Cor/Syn/Sem; Rep only after repair) ==="
COMPARE_TEX_EXTRA=()
TEX_SUFFIX=""
if [ -n "$MODEL" ]; then
  TEX_SUFFIX="$MODEL"
elif [ -n "$OUT_ROOT" ]; then
  TEX_SUFFIX="$(basename "$OUT_ROOT")"
fi
if [ -n "$TEX_SUFFIX" ]; then
  COMPARE_TEX_EXTRA=(--tex-suffix "$TEX_SUFFIX")
  echo "[tex] Writing: result/with_vs_no_test_by_predicate_${TEX_SUFFIX}.tex"
fi
python3 RQ2_Validation/english_to_alloy/compare_with_vs_without_test.py "${COMPARE_TEX_EXTRA[@]}" "${COMPARE_COR_ONLY[@]}"

echo ""
if [ -n "$TEX_SUFFIX" ]; then
  echo "Done. LaTeX: result/with_vs_no_test_by_predicate_${TEX_SUFFIX}.tex"
else
  echo "Done. LaTeX: result/with_vs_no_test_by_predicate.tex"
fi
