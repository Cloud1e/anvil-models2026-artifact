#!/bin/bash
# Alloy-to-Alloy: run LLM-based syntax-fix pipeline for WithTest and NoTest.
# Run from project root. By default stdout/stderr are teed to
# logs/fix_syntax_alloy2alloy_YYYYMMDD_HHMMSS.log.
#
# Usage (from project root):
#   bash scripts/with_vs_without_test/alloy_to_alloy/run_fix_syntax_alloy2alloy.sh
#   bash scripts/with_vs_without_test/alloy_to_alloy/run_fix_syntax_alloy2alloy.sh --limit 2
#   bash scripts/with_vs_without_test/alloy_to_alloy/run_fix_syntax_alloy2alloy.sh --dry-run
#   bash scripts/with_vs_without_test/alloy_to_alloy/run_fix_syntax_alloy2alloy.sh --no-log
#   bash scripts/with_vs_without_test/alloy_to_alloy/run_fix_syntax_alloy2alloy.sh --skip-eval  # skip Java eval if SynItems already exist
#   # any other args are passed through to fix_syntax_llm.py (e.g. --model, --max-iter)
#
# Prerequisites:
#   - result/Gemini/ARepair_Alloy2Alloy_WithTest/responses/<model>.txt and NoTest (LLM responses)
#   - Maven/Java for evaluation
#   - Python: pip install google-generativeai; key in env or .env for syntax fix

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
cd "$PROJECT_DIR"

# Tee to log file unless --no-log or already logging
if [ -z "$A2A_SYN_LOG" ] && [[ " $* " != *" --no-log "* ]]; then
  mkdir -p "$PROJECT_DIR/logs"
  LOG_NAME="fix_syntax_alloy2alloy_$(date +%Y%m%d_%H%M%S).log"
  LOG_PATH="$PROJECT_DIR/logs/$LOG_NAME"
  echo "Log: $LOG_PATH"
  exec env A2A_SYN_LOG="$LOG_PATH" bash "$0" "$@" 2>&1 | tee "$LOG_PATH"
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

# Step 1: Run evaluation so Java writes Alloy/ and Alloy/SynItems/ (when there are Syn). Skip if --skip-eval.
if [ "$SKIP_EVAL" = true ]; then
  echo "=== Skipping evaluation (--skip-eval); using existing Alloy/ and SynItems/ ==="
else
  EVAL_FILTER='^(=== Debug for|Predicates to repair: \[|Other predicates \(not repaired\)|Response line:|Extracted predName:|Extracted predBody:|Predicate signature |Predicate section in test|Other predicates string length|SLF4J:|[0-9][0-9]:[0-9][0-9]:[0-9][0-9]\.[0-9]+.*INFO  kodkod|DEBUG: |Command for first test|Test test[0-9]+: expected|^Solutions$|^false$|^SAME_CODE$|^Correct$|^Wrong$|^Syntax Error$|Detailed test report written to)'
  EVAL_LOG=$(mktemp)
  trap "rm -f '$EVAL_LOG'" EXIT
  echo "=== Alloy-to-Alloy: Evaluate WithTest + NoTest (Java) ==="
  python scripts/with_vs_without_test/alloy_to_alloy/evaluate_alloy2alloy_responses.py > "$EVAL_LOG" 2>&1
  EVAL_EC=$?
  grep -v -E "$EVAL_FILTER" "$EVAL_LOG" || true
  [ "$EVAL_EC" -ne 0 ] && exit "$EVAL_EC"
fi

echo ""
echo "=== Alloy-to-Alloy: LLM syntax fix (WithTest) ==="
python -u scripts/with_vs_without_test/alloy_to_alloy/fix_syntax_llm.py \
  ARepair_Alloy2Alloy_WithTest "${EXTRA_ARGS[@]}"

echo ""
echo "=== Alloy-to-Alloy: LLM syntax fix (NoTest) ==="
python -u scripts/with_vs_without_test/alloy_to_alloy/fix_syntax_llm.py \
  ARepair_Alloy2Alloy_NoTest "${EXTRA_ARGS[@]}"

echo ""
echo "Done syntax-fix runs for WithTest and NoTest."
[ -n "$A2A_SYN_LOG" ] && echo "Full log: $A2A_SYN_LOG"

