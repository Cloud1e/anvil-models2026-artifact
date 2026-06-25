#!/bin/bash
# Experiment 4: Alloy-to-Alloy for faulty models using LLM + ARepair.
# End-to-end pipeline:
#   1) On the host: call Gemini to rewrite faulty predicates (still faulty, different syntax)
#   2) Inside Docker (arepair container): run ARepair on
#        - original faulty models
#        - LLM-rewritten faulty models
#
# Usage (from repo root):
#   # Default (safe): classification only (Step 1.5), no generation, no ARepair
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --model gemini-3.1-pro-preview
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --model gemini-2.5-flash --limit 1
#   # Full pipeline (generation + classification + ARepair)
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --run-llm --run-arepair
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --skip-llm
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --model gemini-3-flash-preview --run-tag 20260322_153045
#
# Notes:
#   - Requires google-genai and a valid GOOGLE_API_KEY or GEMINI_API_KEY (for the host LLM step).
#   - Uses ARepair/experiments/test-suite/<model>.als as test suites.
#   - ARepair itself (run_arepair.py) runs inside the arepair Docker container,
#     similar to scripts/with_vs_without_test/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# This file lives in scripts/thesis/RQ2_FaultyRewrite_ARepair/ → repo root is three levels up.
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
cd "$PROJECT_DIR"
# shellcheck disable=SC1091
source "$ARTIFACT_ROOT/lib/docker_paths.sh"

PYTHON="${PYTHON:-python}"
RQ2_DIR="$ARTIFACT_ROOT/RQ3_Repair"

# If not running inside Docker, do host-side LLM step and then start the arepair container.
if [ "$1" != "--in-docker" ]; then
  MODEL="gemini-3.1-pro-preview"
  LIMIT=0
  # Default behavior is "classification only":
  # - do not generate new LLM rewrites (no touching .als outputs)
  # - do not run ARepair (repair is expensive)
  SKIP_LLM=true
  SKIP_AREPAIR=true
  OUT_ROOT=""
  RUN_TAG=""

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
      --run-tag)
        RUN_TAG="$2"
        shift 2
        ;;
      --limit)
        LIMIT="$2"
        shift 2
        ;;
      --run-llm)
        SKIP_LLM=false
        shift 1
        ;;
      --skip-llm)
        SKIP_LLM=true
        shift 1
        ;;
      --run-arepair)
        SKIP_AREPAIR=false
        shift 1
        ;;
      --skip-arepair)
        SKIP_AREPAIR=true
        shift 1
        ;;
      --full)
        SKIP_LLM=false
        SKIP_AREPAIR=false
        shift 1
        ;;
      *)
        echo "Unknown argument: $1"
        echo "Usage: bash $RQ2_DIR/run_faulty_rewrite_pipeline.sh [--model <gemini-model>] [--out-root <path>] [--run-tag <id>] [--limit N] [--run-llm|--skip-llm] [--run-arepair|--skip-arepair] [--full]"
        exit 1
        ;;
    esac
  done

  # Isolate each run under .../FaultyRewrite/<model>/runs/<tag>/ (no overwrite of prior artifacts).
  if [[ -n "$RUN_TAG" && -z "$OUT_ROOT" ]]; then
    OUT_ROOT="result/Gemini/RQ3_Repair/FaultyRewrite/${MODEL}/runs/${RUN_TAG}"
    echo "[faulty] Using isolated output: $OUT_ROOT"
  fi

  mkdir -p "$PROJECT_DIR/logs"
  LOG_NAME="faulty_rewrite_$(date +%Y%m%d_%H%M%S).log"
  LOG_PATH="$PROJECT_DIR/logs/$LOG_NAME"

  COMPOSE_FILE="$PROJECT_DIR/docker-compose.arepair.yml"
  if [ ! -f "$COMPOSE_FILE" ]; then
    echo "Error: docker-compose.arepair.yml not found."
    exit 1
  fi

  echo "Running faulty-model Alloy-to-Alloy + ARepair pipeline. Log: $LOG_PATH"

  # Must match run_faulty_rewrite.py default when --out-root is omitted.
  if [ -n "$OUT_ROOT" ]; then
    INFO_ROOT="$OUT_ROOT"
  else
    INFO_ROOT="result/Gemini/RQ3_Repair/FaultyRewrite/$MODEL"
  fi

  (
    if [ "$SKIP_LLM" != "true" ]; then
      echo "=== Step 1 (host): LLM predicate rewrite on faulty models (10 rewrites per predicate) ==="
      "$PYTHON" -u "$RQ2_DIR/run_faulty_rewrite.py" --model "$MODEL" ${OUT_ROOT:+--out-root "$OUT_ROOT"} ${LIMIT:+--limit "$LIMIT"}
      echo ""
    else
      echo "=== Step 1 (host): Skipped LLM predicate rewrite (default / --skip-llm) ==="
      echo ""
    fi

    echo "=== Step 1.5 (host): Classify faulty models as Cor/Syn/Sem before ARepair ==="
    echo "[faulty] classify --info-root $INFO_ROOT"
    "$PYTHON" -u "$RQ2_DIR/classify_faulty_models.py" --info-root "$INFO_ROOT"
    ORIG_INFO="$INFO_ROOT/repair_info_original.json"
    LLM_INFO="$INFO_ROOT/repair_info_llm.json"

    if [ "$SKIP_AREPAIR" = "true" ]; then
      echo ""
      echo "=== Step 2+3: Skipped ARepair (default / --skip-arepair) ==="
      exit 0
    fi

    if [ ! -f "$ORIG_INFO" ] || [ ! -f "$LLM_INFO" ]; then
      echo "repair_info JSON not found under $INFO_ROOT; aborting ARepair steps."
      exit 0
    fi

    echo ""
    echo "=== Step 2+3: Run ARepair inside Docker (arepair container) ==="
    REL_INFO_ROOT="$(repo_relpath "$PROJECT_DIR" "$INFO_ROOT")"
    DOCKER_RQ2_E=()
    [[ -n "${REPAIR_FILTER:-}" ]] && DOCKER_RQ2_E+=(-e "REPAIR_FILTER=$REPAIR_FILTER")
    docker-compose -f "$COMPOSE_FILE" run --rm "${DOCKER_RQ2_E[@]}" arepair bash -c \
      "cd /workspace && bash RQ3_Repair/run_faulty_rewrite_pipeline.sh --in-docker --model \"$MODEL\" --out-root \"$REL_INFO_ROOT\""
    echo ""
    echo "Done faulty-model Alloy-to-Alloy + ARepair pipeline."
  ) 2>&1 | tee "$LOG_PATH"

  exit 0
fi

# --- From here we are inside Docker (--in-docker) ---
shift
cd /workspace
# shellcheck disable=SC1091
source /workspace/lib/docker_paths.sh

MODEL="gemini-3.1-pro-preview"
OUT_ROOT=""

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
    *)
      echo "Unknown argument (in-docker): $1"
      exit 1
      ;;
  esac
done

if [ -n "$OUT_ROOT" ]; then
  INFO_ROOT="$OUT_ROOT"
else
  INFO_ROOT="result/Gemini/RQ3_Repair/FaultyRewrite/$MODEL"
fi
docker_normalize_repo_rel INFO_ROOT || exit 1
ORIG_INFO="$INFO_ROOT/repair_info_original.json"
LLM_INFO="$INFO_ROOT/repair_info_llm.json"

if [ ! -f "$ORIG_INFO" ] || [ ! -f "$LLM_INFO" ]; then
  echo "repair_info JSON not found under $INFO_ROOT; aborting ARepair steps."
  exit 0
fi

echo ""
echo "=== Step 2 (in Docker): Run ARepair on ORIGINAL faulty models ==="
# Docker image (Dockerfile.arepair) provides python3 only, not `python`.
# REPAIR_FILTER (e.g. from smoke) limits to one benchmark model; run_arepair.py reads it.
cd /workspace/ARepair && ./arepair.sh --build && cd /workspace
REPAIR_INFO_JSON="/workspace/$ORIG_INFO" OUTPUT_DIR="/workspace/$INFO_ROOT/RepairResultsOriginal" \
  python3 -u scripts/arepair/run_arepair.py

echo ""
echo "=== Step 3 (in Docker): Run ARepair on LLM-REWRITTEN faulty models ==="
REPAIR_INFO_JSON="/workspace/$LLM_INFO" OUTPUT_DIR="/workspace/$INFO_ROOT/RepairResultsLLM" \
  python3 -u scripts/arepair/run_arepair.py

echo ""
echo "Done faulty-model Alloy-to-Alloy + ARepair pipeline (inside Docker)."


