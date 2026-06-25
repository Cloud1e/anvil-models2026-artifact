#!/bin/bash
# English-to-Alloy: run LLM-based syntax-fix pipeline for WithTest and NoTest.
# Reuse the generic fix_syntax_llm.py (under alloy_to_alloy/) to repair Syn items
# produced by the standard ARepair English-to-Alloy evaluation.
#
# Run from project root. By default stdout/stderr are teed to
# logs/fix_syntax_etoa_YYYYMMDD_HHMMSS.log.
#
# Usage (from project root):
#   bash scripts/with_vs_without_test/english_to_alloy/run_fix_syntax_etoa.sh
#   bash scripts/with_vs_without_test/english_to_alloy/run_fix_syntax_etoa.sh --limit 2
#   bash scripts/with_vs_without_test/english_to_alloy/run_fix_syntax_etoa.sh --dry-run
#   bash scripts/with_vs_without_test/english_to_alloy/run_fix_syntax_etoa.sh --no-log
#   bash scripts/with_vs_without_test/english_to_alloy/run_fix_syntax_etoa.sh --skip-eval  # skip Java eval if SynItems already exist
#   # any other args are passed through to fix_syntax_llm.py (e.g. --model, --max-iter)
#
# Prerequisites:
#   - result/Gemini/ARepair/responses/<model>.txt and ARepairNoTest/responses/ (LLM responses)
#   - Maven/Java for evaluation
#   - Python: google-genai + key in env or .env for syntax fix

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
cd "$PROJECT_DIR"

# Tee to log file unless --no-log or already logging
if [ -z "$ETOA_SYN_LOG" ] && [[ " $* " != *" --no-log "* ]]; then
  mkdir -p "$PROJECT_DIR/logs"
  LOG_NAME="fix_syntax_etoa_$(date +%Y%m%d_%H%M%S).log"
  LOG_PATH="$PROJECT_DIR/logs/$LOG_NAME"
  echo "Log: $LOG_PATH"
  exec env ETOA_SYN_LOG="$LOG_PATH" bash "$0" "$@" 2>&1 | tee "$LOG_PATH"
fi

# Parse args for fix_syntax_llm.py (skip --no-log, --skip-eval)
EXTRA_ARGS=()
SKIP_EVAL=false
for x in "$@"; do
  case "$x" in
    --no-log) ;;
    --skip-eval) SKIP_EVAL=true ;;
    *) EXTRA_ARGS+=("$x");;
  esac
done

# Step 1: Run evaluation so Java writes Alloy/ and Alloy/SynItems/ (when there are Syn).
# Skip if --skip-eval. Filter noisy Alloy/Kodkod logs (similar to Alloy-to-Alloy pipeline).
if [ "$SKIP_EVAL" = true ]; then
  echo "=== Skipping evaluation (--skip-eval); using existing ARepair/Alloy and ARepairNoTest/Alloy SynItems ==="
else
  EVAL_FILTER='^(=== Debug for|Predicates to repair: \[|Other predicates \(not repaired\)|Response line:|Extracted predName:|Extracted predBody:|Predicate signature |Predicate section in test|Other predicates string length|SLF4J:|[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]+.*INFO  kodkod|DEBUG: |Command for first test|Test test[0-9]+: expected|^Solutions$|^false$|^SAME_CODE$|^Correct$|^Wrong$|^Syntax Error$|Detailed test report written to)'
  EVAL_LOG=$(mktemp)
  trap "rm -f '$EVAL_LOG'" EXIT
  echo "=== English-to-Alloy: Evaluate WithTest (ARepair) + NoTest (ARepairNoTest) ==="
  (
    bash scripts/with_vs_without_test/english_to_alloy/restore_withtest_alloy.sh
    echo ""
    python -u scripts/with_vs_without_test/english_to_alloy/evaluate_notest_responses.py
  ) > "$EVAL_LOG" 2>&1
  EVAL_EC=$?
  grep -v -E "$EVAL_FILTER" "$EVAL_LOG" || true
  [ "$EVAL_EC" -ne 0 ] && exit "$EVAL_EC"
fi

echo ""
echo "=== English-to-Alloy: LLM syntax fix (WithTest, subfolder=ARepair) ==="
python -u scripts/with_vs_without_test/alloy_to_alloy/fix_syntax_llm.py \
  ARepair "${EXTRA_ARGS[@]}"

echo ""
echo "=== English-to-Alloy: LLM syntax fix (NoTest, subfolder=ARepairNoTest) ==="
python -u scripts/with_vs_without_test/alloy_to_alloy/fix_syntax_llm.py \
  ARepairNoTest "${EXTRA_ARGS[@]}"

echo ""
echo "Done English-to-Alloy syntax-fix runs for WithTest and NoTest."
[ -n "$ETOA_SYN_LOG" ] && echo "Full log: $ETOA_SYN_LOG"

