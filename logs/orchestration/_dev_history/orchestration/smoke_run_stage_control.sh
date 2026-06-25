#!/usr/bin/env bash

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_ID="smoke_$(date +%Y%m%d_%H%M%S)"
MASTER_LOG="$SCRIPT_DIR/smoke_master_${RUN_ID}.log"
SUMMARY_LOG="$SCRIPT_DIR/smoke_summary_${RUN_ID}.log"

run_stage() {
  local name="$1"
  local log_path="$2"
  shift 2
  local ec=0
  echo "[$(date)] START ${name}" | tee -a "$MASTER_LOG" "$SUMMARY_LOG"
  {
    echo "RUN_ID=$RUN_ID"
    echo "STAGE=$name"
    echo "PWD=$(pwd)"
    echo "COMMAND=$*"
    echo
    "$@"
    ec=$?
    echo
    echo "STAGE_EXIT_CODE=$ec"
  } >"$log_path" 2>&1
  echo "[$(date)] END ${name} exit=${ec} log=${log_path}" | tee -a "$MASTER_LOG" "$SUMMARY_LOG"
  return 0
}

echo "RUN_ID=$RUN_ID" > "$MASTER_LOG"
echo "MASTER_LOG=$MASTER_LOG" >> "$MASTER_LOG"
echo "SUMMARY_LOG=$SUMMARY_LOG" >> "$MASTER_LOG"

run_stage "SUCCESS_ONLY_1" "$SCRIPT_DIR/smoke_success_1_${RUN_ID}.log" bash -c 'sleep 1; echo stage1 done'
run_stage "SUCCESS_ONLY_2" "$SCRIPT_DIR/smoke_success_2_${RUN_ID}.log" bash -c 'sleep 1; echo stage2 done'
run_stage "SUCCESS_ONLY_3" "$SCRIPT_DIR/smoke_success_3_${RUN_ID}.log" bash -c 'sleep 1; echo stage3 done'

run_stage "FAILURE_CONTINUE_1" "$SCRIPT_DIR/smoke_failure_1_${RUN_ID}.log" bash -c 'sleep 1; echo before failure'
run_stage "FAILURE_CONTINUE_2" "$SCRIPT_DIR/smoke_failure_2_${RUN_ID}.log" bash -c 'sleep 1; echo intentional failure; exit 7'
run_stage "FAILURE_CONTINUE_3" "$SCRIPT_DIR/smoke_failure_3_${RUN_ID}.log" bash -c 'sleep 1; echo after failure'

echo "[$(date)] SMOKE_DONE ${RUN_ID}" | tee -a "$MASTER_LOG" "$SUMMARY_LOG"
echo "$RUN_ID"
