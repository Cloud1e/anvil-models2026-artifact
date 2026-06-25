#!/usr/bin/env bash
# Consolidate final reviewer-facing entrypoints and run quick validation.

set -u
trap '' HUP

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$ARTIFACT_ROOT" || exit 1

RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
ORCH_DIR="$ARTIFACT_ROOT/logs/orchestration"
DEV_HISTORY="$ORCH_DIR/_dev_history"
REPORT="$ORCH_DIR/consolidate_final_scripts_report.log"
RUN_LOG_DIR="$ORCH_DIR/final_scripts_quick_${RUN_ID}"
mkdir -p "$DEV_HISTORY/scripts" "$DEV_HISTORY/orchestration" "$RUN_LOG_DIR"

log() {
  echo "[$(date)] $*" | tee -a "$REPORT"
}

run_step() {
  local name="$1"
  shift
  local log_path="$RUN_LOG_DIR/${name}.log"
  local ec=0
  log "START ${name}: $*"
  {
    echo "RUN_ID=$RUN_ID"
    echo "STEP=$name"
    echo "PWD=$(pwd)"
    echo "COMMAND=$*"
    echo
    "$@"
    ec=$?
    echo
    echo "STEP_EXIT_CODE=$ec"
  } >"$log_path" 2>&1
  log "END ${name} exit=${ec} log=${log_path}"
  return "$ec"
}

archive_path() {
  local p="$1"
  local dest_dir="$2"
  if [ -e "$p" ]; then
    mkdir -p "$dest_dir"
    local base
    base="$(basename "$p")"
    local dest="$dest_dir/$base"
    if [ -e "$dest" ]; then
      dest="$dest_dir/${base}.${RUN_ID}"
    fi
    mv "$p" "$dest"
    log "ARCHIVED $p -> $dest"
  fi
}

: > "$REPORT"
log "Consolidating final scripts"
log "Artifact root: $ARTIFACT_ROOT"

log "Final entrypoints:"
log "  RQ1_Generation/run.sh --quick|--full"
log "  RQ2_Validation/run.sh --quick|--full"
log "  RQ3_Repair/run.sh --quick|--full"
chmod +x RQ1_Generation/run.sh RQ2_Validation/run.sh RQ3_Repair/run.sh

log "Syntax checks"
run_step syntax_checks bash -lc \
  "bash -n RQ1_Generation/run.sh && bash -n RQ2_Validation/run.sh && bash -n RQ3_Repair/run.sh && python3 -m py_compile RQ3_Repair/classify_faulty_models.py"
syntax_ec=$?

log "Archiving historical debug scripts"
archive_path "scripts/run_overnight_sequential.sh" "$DEV_HISTORY/scripts"
archive_path "scripts/run_rq2_rq3_sequential.sh" "$DEV_HISTORY/scripts"
archive_path "scripts/run_rq3_oracle_fix_and_rq2_ab.sh" "$DEV_HISTORY/scripts"
archive_path "logs/orchestration/smoke_run_stage_control.sh" "$DEV_HISTORY/orchestration"

log "Archiving historical debug logs and scratch directories"
python3 - <<'PY' "$ORCH_DIR" "$DEV_HISTORY/orchestration" "$RUN_ID" "$REPORT"
import shutil
import sys
from pathlib import Path

orch = Path(sys.argv[1])
dest_root = Path(sys.argv[2])
run_id = sys.argv[3]
report = Path(sys.argv[4])

keep_names = {
    "consolidate_final_scripts_report.log",
    "paper_artifact_diff_latest.csv",
    "paper_artifact_diff_latest_summary.json",
    "rq3_oracle_fix_rq2_ab_launcher_20260623_121045.log",
    "rq3_oracle_fix_rq2_ab_master_20260623_121045.log",
    "rq3_oracle_fix_rq2_ab_summary_20260623_121045.log",
    "RQ3_ORACLE_FIX_RQ2_AB_DONE_20260623_121045.marker",
}
keep_prefixes = {
    f"final_scripts_quick_{run_id}",
    "rq3_oracle_fix_rq2_ab_20260623_121045",
    "_dev_history",
}
patterns = [
    "smoke_*",
    "*single_case*",
    "*batch_test*",
    "rq2_rq3_*",
    "wrapper_*",
    "ALL_DONE_*",
    "overnight_*",
    "paper_artifact_diff_20260622_*",
    "rq3_classification_drift_*",
    "RQ2_RQ3_ALL_DONE_*",
    "rq3_oracle_fix_rq2_ab_*120425*",
    "RQ3_ORACLE_FIX_RQ2_AB_DONE_20260623_120425.marker",
]

def log(msg: str) -> None:
    with report.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def should_keep(path: Path) -> bool:
    name = path.name
    if name in keep_names:
        return True
    return any(name.startswith(prefix) for prefix in keep_prefixes)

seen = set()
for pattern in patterns:
    for path in orch.glob(pattern):
        if path in seen or should_keep(path):
            continue
        seen.add(path)
        dest = dest_root / path.name
        if dest.exists():
            dest = dest_root / f"{path.name}.{run_id}"
        shutil.move(str(path), str(dest))
        log(f"ARCHIVED {path} -> {dest}")
PY

log "Quick validation"
run_step rq1_quick bash RQ1_Generation/run.sh --quick
rq1_ec=$?
run_step rq2_quick bash RQ2_Validation/run.sh --quick
rq2_ec=$?
run_step rq3_quick bash RQ3_Repair/run.sh --quick
rq3_ec=$?

log "Quick Start commands validated:"
log "  bash RQ1_Generation/run.sh --quick"
log "  bash RQ2_Validation/run.sh --quick"
log "  bash RQ3_Repair/run.sh --quick"

log "Full reproduction commands:"
log "  bash RQ1_Generation/run.sh --full"
log "  bash RQ2_Validation/run.sh --full  # internally uses AREPAIR_VALIDATION=testsuite"
log "  bash RQ3_Repair/run.sh --full      # classification primary is Example --check-one"

if [ "$syntax_ec" -eq 0 ] && [ "$rq1_ec" -eq 0 ] && [ "$rq2_ec" -eq 0 ] && [ "$rq3_ec" -eq 0 ]; then
  log "RESULT success: final scripts consolidated and quick validation passed"
  exit 0
fi

log "RESULT failure: syntax=${syntax_ec} rq1=${rq1_ec} rq2=${rq2_ec} rq3=${rq3_ec}"
exit 1
