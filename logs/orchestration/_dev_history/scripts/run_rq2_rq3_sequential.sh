#!/usr/bin/env bash
# Sequential full rerun for RQ2 and RQ3, followed by paper/artifact diff.
# This script intentionally keeps going after a stage failure so later stages
# still produce diagnostic logs.

trap '' HUP

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ARTIFACT_ROOT" || exit 1

RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
ORCH_DIR="$ARTIFACT_ROOT/logs/orchestration"
RQ2_LOG_DIR="$ARTIFACT_ROOT/RQ2_Validation/logs"
RQ3_LOG_DIR="$ARTIFACT_ROOT/RQ3_Repair/logs"
mkdir -p "$ORCH_DIR" "$RQ2_LOG_DIR" "$RQ3_LOG_DIR"

MASTER_LOG="$ORCH_DIR/rq2_rq3_master_${RUN_ID}.log"
SUMMARY_LOG="$ORCH_DIR/rq2_rq3_summary_${RUN_ID}.log"
DONE_MARKER="$ORCH_DIR/RQ2_RQ3_ALL_DONE_${RUN_ID}.marker"
RESUME_SUMMARY_LOGS="${RESUME_SUMMARY_LOGS:-${RESUME_SUMMARY_LOG:-}}"

MODELS=(
  "gemini-3.1-pro-preview"
  "gemini-3-flash-preview"
  "gemini-3.1-flash-lite-preview"
)

compose_cmd() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

stage_completed_in_log() {
  local name="$1"
  local summary="$2"
  local allow_legacy_a2a_exit1="${3:-0}"

  [ -n "$summary" ] || return 1
  [ -f "$summary" ] || return 1

  if grep -F "END ${name} exit=0 " "$summary" >/dev/null 2>&1; then
    return 0
  fi

  # The 20260622_154410 run had a harmless A2A trailer bug that made fully
  # completed A2A stages report exit=1. Only accept that for explicit resume
  # logs, not for this run's current summary.
  if [ "$allow_legacy_a2a_exit1" -eq 1 ] && [[ "$name" == RQ2_A2A_* ]]; then
    grep -F "END ${name} exit=1 " "$summary" >/dev/null 2>&1
    return $?
  fi

  return 1
}

stage_completed() {
  local name="$1"

  if stage_completed_in_log "$name" "$SUMMARY_LOG" 0; then
    return 0
  fi

  local old_ifs="$IFS"
  local summary
  IFS=':'
  for summary in $RESUME_SUMMARY_LOGS; do
    IFS="$old_ifs"
    if stage_completed_in_log "$name" "$summary" 1; then
      return 0
    fi
    IFS=':'
  done
  IFS="$old_ifs"

  return 1
}

run_stage() {
  local name="$1"
  local log_path="$2"
  shift 2
  local ec=0

  if stage_completed "$name"; then
    echo "[$(date)] SKIP ${name}, already completed" | tee -a "$MASTER_LOG" "$SUMMARY_LOG"
    return 0
  fi

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

{
  echo "RUN_ID=$RUN_ID"
  echo "ARTIFACT_ROOT=$ARTIFACT_ROOT"
  echo "RQ2_LOG_DIR=$RQ2_LOG_DIR"
  echo "RQ3_LOG_DIR=$RQ3_LOG_DIR"
  echo "ORCH_DIR=$ORCH_DIR"
  echo "RESUME_SUMMARY_LOGS=$RESUME_SUMMARY_LOGS"
  echo "PID=$$"
  echo "PPID=$PPID"
  echo "START=$(date)"
} > "$MASTER_LOG"

export AREPAIR_VALIDATION="${AREPAIR_VALIDATION:-testsuite}"
export TIMEOUT="${TIMEOUT:-600}"

for model in "${MODELS[@]}"; do
  run_stage \
    "RQ2_E2A_${model}" \
    "$RQ2_LOG_DIR/rq2_e2a_${model}_${RUN_ID}.log" \
    env AREPAIR_VALIDATION="$AREPAIR_VALIDATION" TIMEOUT="$TIMEOUT" \
      THESIS_LOG_FILE="$RQ2_LOG_DIR/rq2_e2a_inner_${model}_${RUN_ID}.log" \
      bash RQ2_Validation/english_to_alloy/run_rq1_e2a_full_host.sh \
      "result/Gemini/RQ2_Validation/E2A/${model}"

  run_stage \
    "RQ2_A2A_${model}" \
    "$RQ2_LOG_DIR/rq2_a2a_${model}_${RUN_ID}.log" \
    compose_cmd -f docker-compose.arepair.yml run --rm arepair bash -c \
      "set -o pipefail; cd /workspace && export AREPAIR_VALIDATION=${AREPAIR_VALIDATION} TIMEOUT=${TIMEOUT}; bash RQ2_Validation/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh --in-docker --model ${model} --out-root result/Gemini/RQ2_Validation/A2A/${model}"
done

for model in "${MODELS[@]}"; do
  run_stage \
    "RQ3_${model}" \
    "$RQ3_LOG_DIR/rq3_faulty_rewrite_${model}_${RUN_ID}.log" \
    bash RQ3_Repair/run_faulty_rewrite_pipeline.sh \
      --model "$model" \
      --out-root "result/Gemini/RQ3_Repair/FaultyRewrite/${model}/ARepair_FaultyRewrite" \
      --skip-llm \
      --run-arepair
done

run_stage \
  "DIFF_COMPARE" \
  "$ORCH_DIR/compare_paper_artifact_${RUN_ID}.log" \
  python3 scripts/compare_paper_artifact.py

{
  echo "RUN_ID=$RUN_ID"
  echo "FINISH=$(date)"
  echo "MASTER_LOG=$MASTER_LOG"
  echo "SUMMARY_LOG=$SUMMARY_LOG"
  echo "DIFF_SUMMARY=$ORCH_DIR/paper_artifact_diff_latest_summary.json"
} > "$DONE_MARKER"

echo "[$(date)] ALL DONE marker=${DONE_MARKER}" | tee -a "$MASTER_LOG" "$SUMMARY_LOG"
