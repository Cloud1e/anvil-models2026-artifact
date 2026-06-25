#!/bin/bash
#
# Compare ARepair results: original test suite vs extended test suite (combined_tests.als)
# Works both locally and in Docker (project mounted at /workspace).
#
# Usage:
#   ./scripts/arepair/compare_test_suites_arepair.sh [model_name]
#
# Example:
#   ./scripts/arepair/compare_test_suites_arepair.sh arr1
#
# Or in Docker:
#   docker-compose -f docker-compose.arepair.yml run --rm arepair bash scripts/arepair/compare_test_suites_arepair.sh arr1
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Docker mounts project at /workspace; otherwise use project root (two levels up from scripts/arepair/)
if [ -d "/workspace" ]; then
    PROJECT_DIR="/workspace"
else
    ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
fi

MODEL_NAME="${1:-arr1}"
AREPAIR_DIR="${PROJECT_DIR}/ARepair"
REALBUGS_DIR="${AREPAIR_DIR}/experiments/realbugs"
TEST_SUITE_DIR="${AREPAIR_DIR}/experiments/test-suite"
TESTGEN_TESTS_DIR="${PROJECT_DIR}/testgen/tests"
COMPARISON_DIR="${PROJECT_DIR}/testgen/comparison"

# ARepair params (same as models.sh for arr1)
SCOPE="${SCOPE:-3}"
MIN_COST="${MIN_COST:-3}"
SEARCH_STRATEGY="${SEARCH_STRATEGY:-base-choice}"
MAX_TRY_PER_HOLE="${MAX_TRY_PER_HOLE:-1000}"

# Model -> testgen folder mapping (model_pred for combined_tests.als)
get_testgen_folder() {
    case "$1" in
        arr1|arr2) echo "arr_NoConflict" ;;
        balancedBST*) echo "balancedBST_HasAtMostOneChild" ;;
        cd1|cd2) echo "cd_Acyclic" ;;
        dll*) echo "dll_ConsistentPreAndNxt" ;;
        gradeFaulty) echo "grade_PolicyAllowsGrading" ;;
        student*) echo "student_Sorted" ;;
        *) echo "" ;;
    esac
}

# Resolve model file
MODEL_FILE="${REALBUGS_DIR}/${MODEL_NAME}.als"
if [ ! -f "$MODEL_FILE" ]; then
    echo "ERROR: Model not found: $MODEL_FILE"
    echo "Available: $(ls "$REALBUGS_DIR" 2>/dev/null | head -20)"
    exit 1
fi

TESTGEN_FOLDER=$(get_testgen_folder "$MODEL_NAME")
EXTENDED_TEST="${TESTGEN_TESTS_DIR}/${TESTGEN_FOLDER}/combined_tests.als"

if [ -z "$TESTGEN_FOLDER" ] || [ ! -f "$EXTENDED_TEST" ]; then
    echo "ERROR: No extended test suite for $MODEL_NAME (expected: $EXTENDED_TEST)"
    echo "Available testgen folders: $(ls "$TESTGEN_TESTS_DIR" 2>/dev/null)"
    exit 1
fi

# Original test: arr1 -> arr.als, balancedBST1 -> balancedBST.als, gradeFaulty -> grade.als, etc.
BASE_MODEL=$(echo "$MODEL_NAME" | sed 's/[0-9]*$//' | sed 's/Faulty$//')
ORIGINAL_TEST="${TEST_SUITE_DIR}/${BASE_MODEL}.als"
if [ ! -f "$ORIGINAL_TEST" ]; then
    echo "ERROR: Original test not found: $ORIGINAL_TEST"
    exit 1
fi

mkdir -p "$COMPARISON_DIR"

run_arepair() {
    local label="$1"
    local model_path="$2"
    local test_path="$3"
    local log_file="$4"
    local fix_dest="$5"

    echo ""
    echo "=== Running ARepair with $label ==="
    echo "  Model: $model_path"
    echo "  Test:  $test_path"
    echo "  Log:   $log_file"

    local model_abs test_abs
    model_abs="$(cd "$PROJECT_DIR" && realpath "$model_path")"
    test_abs="$(cd "$PROJECT_DIR" && realpath "$test_path")"
    (cd "$AREPAIR_DIR" && bash arepair.sh --run \
        -m "$model_abs" \
        -t "$test_abs" \
        -s "$SCOPE" \
        -c "$MIN_COST" \
        -g "$SEARCH_STRATEGY" \
        -h "$MAX_TRY_PER_HOLE") > "$log_file" 2>&1
    local ret=$?
    cat "$log_file"

    if [ -f "${AREPAIR_DIR}/.hidden/fix.als" ]; then
        cp "${AREPAIR_DIR}/.hidden/fix.als" "$fix_dest"
        echo "  Fixed model saved: $fix_dest"
    else
        echo "  No fix.als produced"
    fi
    return $ret
}

# --- Run original ---
run_arepair "ORIGINAL test suite" \
    "$MODEL_FILE" \
    "$ORIGINAL_TEST" \
    "${COMPARISON_DIR}/${MODEL_NAME}_original.log" \
    "${COMPARISON_DIR}/${MODEL_NAME}_original_fix.als" || true

# --- Run extended ---
run_arepair "EXTENDED test suite (combined_tests.als)" \
    "$MODEL_FILE" \
    "$EXTENDED_TEST" \
    "${COMPARISON_DIR}/${MODEL_NAME}_extended.log" \
    "${COMPARISON_DIR}/${MODEL_NAME}_extended_fix.als" || true

# --- Summary ---
echo ""
echo "=== Comparison Summary for $MODEL_NAME ==="
echo ""
echo "Original test: $ORIGINAL_TEST"
echo "Extended test: $EXTENDED_TEST"
echo ""
echo "Logs:"
echo "  Original: ${COMPARISON_DIR}/${MODEL_NAME}_original.log"
echo "  Extended: ${COMPARISON_DIR}/${MODEL_NAME}_extended.log"
echo ""
echo "Fixed models (if produced):"
echo "  Original: ${COMPARISON_DIR}/${MODEL_NAME}_original_fix.als"
echo "  Extended: ${COMPARISON_DIR}/${MODEL_NAME}_extended_fix.als"
echo ""
echo "To inspect: tail -100 ${COMPARISON_DIR}/${MODEL_NAME}_original.log"
echo "            tail -100 ${COMPARISON_DIR}/${MODEL_NAME}_extended.log"
echo ""
echo "Done."
