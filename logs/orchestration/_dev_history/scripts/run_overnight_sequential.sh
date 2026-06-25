#!/usr/bin/env bash

# Intentionally do not use `set -e`: an overnight failure in one RQ should not
# prevent later RQs from running and producing useful logs.
trap '' HUP

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="$ARTIFACT_ROOT/logs"
RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"

mkdir -p "$LOG_DIR"

RQ1_LOG="$LOG_DIR/rq1_overnight_${RUN_ID}.log"
RQ2_LOG="$LOG_DIR/rq2_overnight_${RUN_ID}.log"
RQ3_LOG="$LOG_DIR/rq3_overnight_${RUN_ID}.log"
SUMMARY_LOG="$LOG_DIR/overnight_summary_${RUN_ID}.log"
DONE_MARKER="$LOG_DIR/ALL_DONE_${RUN_ID}.marker"

export ARTIFACT_ROOT LOG_DIR RUN_ID

{
  echo "RUN_ID=$RUN_ID"
  echo "ARTIFACT_ROOT=$ARTIFACT_ROOT"
  echo "RQ1_LOG=$RQ1_LOG"
  echo "RQ2_LOG=$RQ2_LOG"
  echo "RQ3_LOG=$RQ3_LOG"
  echo "SUMMARY_LOG=$SUMMARY_LOG"
  echo "DONE_MARKER=$DONE_MARKER"
} > "$LOG_DIR/overnight_latest_paths.env"

log_master() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

run_stage() {
  local stage="$1"
  local log_file="$2"
  local command_text="$3"
  local started_at finished_at exit_code

  started_at="$(date '+%Y-%m-%d %H:%M:%S')"
  log_master "Starting ${stage}; log=${log_file}"
  {
    echo "[$started_at] Starting ${stage}"
    echo "ARTIFACT_ROOT=$ARTIFACT_ROOT"
    echo "RUN_ID=$RUN_ID"
    echo
    echo "Command block:"
    echo "$command_text"
    echo
    bash -lc "$command_text"
    exit_code=$?
    finished_at="$(date '+%Y-%m-%d %H:%M:%S')"
    echo
    echo "[$finished_at] ${stage} finished with exit code ${exit_code}"
    echo "STAGE_EXIT_CODE=${exit_code}"
  } > "$log_file" 2>&1

  exit_code=$?
  # The outer redirection succeeded unless the filesystem failed; stage status
  # is written inside the log. Keep wrapper moving regardless.
  log_master "Finished ${stage}; wrapper redirection exit=${exit_code}"
  {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ${stage} log: ${log_file}"
    grep -E "STAGE_EXIT_CODE=" "$log_file" | tail -n 1 || true
  } >> "$SUMMARY_LOG"
}

RQ1_CMD='
cd "$ARTIFACT_ROOT" || exit 1
echo "RQ1 validation standard:"
echo "- Entry points: Example rq1-process-english / rq1-process-alloy."
echo "- Standard: bounded equivalence check, generated as check { P <=> P2 } for 5."
echo "- Cor = SAME_CODE or CORRECT_CODE; Syn = SYNTAX_ERROR; Sem = DIFF_OUTPUT."
echo "- No RQ2-style AREPAIR_VALIDATION testsuite/equivalence branch is used by these RQ1 entry points."
echo
for model in gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview; do
  echo "[$(date)] RQ1 model=${model} E2A+A2A"
  bash RQ1_Generation/eval/run_rq1_eval.sh "$model" both
  ec=$?
  echo "[$(date)] RQ1 model=${model} exit=${ec}"
done
'

RQ2_CMD='
cd "$ARTIFACT_ROOT" || exit 1
export AREPAIR_VALIDATION=testsuite
echo "RQ2 locked validation config: AREPAIR_VALIDATION=${AREPAIR_VALIDATION}"
echo "RQ2 E2A uses run_rq1_e2a_full_host.sh. RQ2 A2A uses in-docker run_with_vs_no_test_alloy2alloy.sh."
echo
for model in gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview; do
  echo "[$(date)] RQ2 E2A model=${model}"
  bash RQ2_Validation/english_to_alloy/run_rq1_e2a_full_host.sh "result/Gemini/RQ2_Validation/E2A/${model}"
  ec=$?
  echo "[$(date)] RQ2 E2A model=${model} exit=${ec}"

  echo "[$(date)] RQ2 A2A model=${model}"
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose -f docker-compose.arepair.yml run --rm arepair bash -c "cd /workspace && export AREPAIR_VALIDATION=testsuite && bash RQ2_Validation/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh --in-docker --model ${model} --out-root result/Gemini/RQ2_Validation/A2A/${model}"
  else
    docker compose -f docker-compose.arepair.yml run --rm arepair bash -c "cd /workspace && export AREPAIR_VALIDATION=testsuite && bash RQ2_Validation/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh --in-docker --model ${model} --out-root result/Gemini/RQ2_Validation/A2A/${model}"
  fi
  ec=$?
  echo "[$(date)] RQ2 A2A model=${model} exit=${ec}"
done
'

RQ3_CMD='
cd "$ARTIFACT_ROOT" || exit 1
echo "RQ3 classification standard:"
echo "- Primary classifier: RQ3_Repair/classify_faulty_models.py -> Rq3ParallelTestSuiteOracle."
echo "- Standard: all test-suite commands must match their expect value; pred-equivalence is only a reference field."
echo "- This stage skips new LLM calls and reruns classification + real ARepair repair on existing rewrites."
echo
for model in gemini-3.1-pro-preview gemini-3-flash-preview gemini-3.1-flash-lite-preview; do
  out_root="result/Gemini/RQ3_Repair/FaultyRewrite/${model}/ARepair_FaultyRewrite"
  echo "[$(date)] RQ3 model=${model} out_root=${out_root}"
  bash RQ3_Repair/run_faulty_rewrite_pipeline.sh --model "$model" --out-root "$out_root" --skip-llm --run-arepair
  ec=$?
  echo "[$(date)] RQ3 model=${model} exit=${ec}"
done
'

log_master "Overnight sequential run started; RUN_ID=${RUN_ID}"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] Overnight sequential run started; RUN_ID=${RUN_ID}" > "$SUMMARY_LOG"

run_stage "RQ1" "$RQ1_LOG" "$RQ1_CMD"
run_stage "RQ2" "$RQ2_LOG" "$RQ2_CMD"
run_stage "RQ3" "$RQ3_LOG" "$RQ3_CMD"

{
  echo "RUN_ID=$RUN_ID"
  echo "Finished at $(date '+%Y-%m-%d %H:%M:%S')"
  echo "RQ1_LOG=$RQ1_LOG"
  echo "RQ2_LOG=$RQ2_LOG"
  echo "RQ3_LOG=$RQ3_LOG"
  echo "SUMMARY_LOG=$SUMMARY_LOG"
} > "$DONE_MARKER"

log_master "All stages attempted; done marker=${DONE_MARKER}"
