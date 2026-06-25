#!/bin/bash
# English-to-Alloy WITH-TEST: temporary pipeline to re-run a small set of models
# with a newer Gemini model (e.g. 3.1 Pro) using the OLD prompts under
# query/Gemini/ARepair, and save responses under:
#   result/Gemini/ETOA_WithTest_3_1_Tmp/responses/
#
# Usage (from project root, in your conda env with google-genai installed):
#   bash scripts/with_vs_without_test/english_to_alloy/run_etoa_withtest_3_1_pipeline.sh \
#     --model YOUR_3_1_PRO_MODEL_NAME
#
# Notes:
# - Prompts are taken from: query/Gemini/ARepair/<model>
# - Responses are written to: result/Gemini/ETOA_WithTest_3_1_Tmp/responses/<model>.txt
# - This script only calls the LLM to generate new responses; it does not run Java evaluation.
#   You can use the outputs to compare 3.0 Pro vs 3.1 Pro (syntax / semantic differences).

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
cd "$PROJECT_DIR"

mkdir -p "$PROJECT_DIR/logs"
TS="$(date +%Y%m%d_%H%M%S)"
LOG_PATH="$PROJECT_DIR/logs/thesis_RQ1_etoa_withtest_3_1_${TS}.log"
exec > >(tee "$LOG_PATH") 2>&1

MODEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --model)
      MODEL="$2"
      shift 2
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [ -z "$MODEL" ]; then
  echo "Please specify --model <GEMINI_MODEL_NAME> (e.g. your 3.1 Pro model)." >&2
  exit 1
fi

OUT_BASE="result/Gemini/ETOA_WithTest_3_1_Tmp/responses"
mkdir -p "$OUT_BASE"

# Run the 9 ARepair WithTest models; edit this list to run only a subset
MODELS=(
  arr
  bempl
  balancedBST
  cd
  dll
  farmer
  grade
  other
  student
)

echo "Project dir: $PROJECT_DIR"
echo "Using Gemini model: $MODEL"
echo "Writing responses to: $OUT_BASE"
echo ""

for m in "${MODELS[@]}"; do
  IN="query/Gemini/ARepair/$m"
  OUT="$OUT_BASE/$m.txt"

  if [ ! -f "$IN" ]; then
    echo "[WARN] Prompt file not found, skip: $IN"
    continue
  fi

  echo "=== Running $m ==="
  echo "Prompt:  $IN"
  echo "Output:  $OUT"

  python scripts/with_vs_without_test/english_to_alloy/run_gemini_etoa_single.py \
    --model "$MODEL" \
    --input "$IN" \
    --output "$OUT"

  echo ""
done

echo "Done. New 3.1 Pro responses are under:"
echo "  $OUT_BASE"

