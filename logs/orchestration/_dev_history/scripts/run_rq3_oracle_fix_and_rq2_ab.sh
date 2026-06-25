#!/usr/bin/env bash
# Serial recovery/diagnostic wrapper:
#  0. verify/restore clean RQ3 classification ground truth inside anvil-artifact
#  1. verify RQ3 classifier uses Example --check-one as primary
#  2. run 21-case gate against internal ground-truth snapshots
#  3. run full classification comparison against internal ground-truth snapshots
#  4. rerun RQ3 repair
#  5. run RQ2 dll_ConsistentPreAndNxt_5 Docker A/B for Patcher top3 logging
#  6. regenerate paper/artifact diff

set -u
trap '' HUP

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$ARTIFACT_ROOT/.." && pwd)"
cd "$ARTIFACT_ROOT" || exit 1

RUN_ID="${RUN_ID:-$(date +%Y%m%d_%H%M%S)}"
ORCH_DIR="$ARTIFACT_ROOT/logs/orchestration"
RUN_DIR="$ORCH_DIR/rq3_oracle_fix_rq2_ab_${RUN_ID}"
GROUND_TRUTH_DIR="$RUN_DIR/rq3_ground_truth"
AB_DIR="$RUN_DIR/rq2_ab_dll_ConsistentPreAndNxt_5"
MASTER_LOG="$ORCH_DIR/rq3_oracle_fix_rq2_ab_master_${RUN_ID}.log"
SUMMARY_LOG="$ORCH_DIR/rq3_oracle_fix_rq2_ab_summary_${RUN_ID}.log"
DONE_MARKER="$ORCH_DIR/RQ3_ORACLE_FIX_RQ2_AB_DONE_${RUN_ID}.marker"
mkdir -p "$RUN_DIR" "$GROUND_TRUTH_DIR" "$AB_DIR"

MODELS=(
  "gemini-3.1-pro-preview"
  "gemini-3-flash-preview"
  "gemini-3.1-flash-lite-preview"
)

log() {
  echo "[$(date)] $*" | tee -a "$MASTER_LOG" "$SUMMARY_LOG"
}

run_logged() {
  local name="$1"
  local log_path="$2"
  shift 2
  local ec=0
  log "START ${name}"
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
  log "END ${name} exit=${ec} log=${log_path}"
  return "$ec"
}

compose_cmd() {
  if command -v docker-compose >/dev/null 2>&1; then
    docker-compose "$@"
  else
    docker compose "$@"
  fi
}

{
  echo "RUN_ID=$RUN_ID"
  echo "ARTIFACT_ROOT=$ARTIFACT_ROOT"
  echo "REPO_ROOT=$REPO_ROOT"
  echo "RUN_DIR=$RUN_DIR"
  echo "PID=$$"
  echo "PPID=$PPID"
  echo "START=$(date)"
} > "$MASTER_LOG"
: > "$SUMMARY_LOG"

log "STEP0 ground-truth gate"
python3 - <<'PY' "$REPO_ROOT" "$ARTIFACT_ROOT" "$GROUND_TRUTH_DIR" "$SUMMARY_LOG"
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

repo = Path(sys.argv[1])
artifact = Path(sys.argv[2])
snapshot_dir = Path(sys.argv[3])
summary_log = Path(sys.argv[4])

models = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
]
clean_sources = {
    # Main pro path was polluted by an earlier rerun; this archive copy has been
    # verified as the 0/1/129 LLM and 0/0/13 original ground truth.
    "gemini-3.1-pro-preview": (
        repo
        / "result/Gemini/archive_thesis_migration/_LEGACY_MIXED/Gemini/RQ3_Repair/FaultyRewrite"
        / "gemini-3.1-pro-preview/ARepair_FaultyRewrite/classification.json"
    ),
    # Flash/lite main paths are still the March check-one ground truth.
    "gemini-3-flash-preview": (
        repo
        / "result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3-flash-preview/ARepair_FaultyRewrite/classification.json"
    ),
    "gemini-3.1-flash-lite-preview": (
        repo
        / "result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3.1-flash-lite-preview/ARepair_FaultyRewrite/classification.json"
    ),
}
known_expected = {
    "gemini-3-flash-preview": {
        "student_Sorted_llm_8": "Sem",
    },
    "gemini-3.1-flash-lite-preview": {
        "dll_ConsistentPreAndNxt_llm_3": "Sem",
        "farmer_crossRiver_llm_8": "Cor",
        "student_Contains_llm_3": "Sem",
        "student_Sorted_llm_4": "Sem",
    },
}

def log(msg: str) -> None:
    print(msg)
    with summary_log.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))

def by_uid(data: dict) -> dict:
    return {item.get("unique_id"): item for item in data.get("results", [])}

def has_fresh_diagnostic_schema(data: dict) -> bool:
    return any(
        "validation" in item or "testsuite_oracle_code_type" in item
        for item in data.get("results", [])[:20]
    )

snapshot_dir.mkdir(parents=True, exist_ok=True)
gate_ok = True
for model in models:
    clean_path = clean_sources[model]
    artifact_path = artifact / "result/Gemini/RQ3_Repair/FaultyRewrite" / model / "ARepair_FaultyRewrite/classification.json"
    log(f"root_candidate {model}: {clean_path}")
    log(f"artifact_candidate {model}: {artifact_path}")
    if not clean_path.is_file():
        log(f"STEP0_FAIL missing root clean candidate for {model}")
        gate_ok = False
        continue
    if not artifact_path.is_file():
        log(f"STEP0_WARN missing artifact classification for {model}; will restore from root if root is clean")

    clean = load(clean_path)
    clean_uid = by_uid(clean)
    root_mtime = datetime.fromtimestamp(clean_path.stat().st_mtime).isoformat(timespec="seconds")
    artifact_mtime = (
        datetime.fromtimestamp(artifact_path.stat().st_mtime).isoformat(timespec="seconds")
        if artifact_path.exists()
        else "MISSING"
    )
    log(f"mtime {model}: root={root_mtime} artifact={artifact_mtime}")

    if has_fresh_diagnostic_schema(clean):
        log(f"STEP0_FAIL root clean candidate for {model} has fresh diagnostic schema; possible pollution")
        gate_ok = False
        continue

    for uid, expected in known_expected.get(model, {}).items():
        actual = clean_uid.get(uid, {}).get("result")
        if actual != expected:
            log(f"STEP0_FAIL root known-result mismatch {model} {uid}: expected={expected} actual={actual}")
            gate_ok = False

    if not gate_ok:
        continue

    polluted = True
    if artifact_path.is_file():
        art = load(artifact_path)
        polluted = has_fresh_diagnostic_schema(art) or by_uid(art) != clean_uid
    if polluted:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(clean_path, artifact_path)
        log(f"STEP0_RESTORED artifact classification from clean root for {model}")
    else:
        log(f"STEP0_CLEAN artifact classification already matches clean root for {model}")

    snapshot_path = snapshot_dir / f"{model}__classification_ground_truth.json"
    shutil.copy2(artifact_path, snapshot_path)
    log(f"STEP0_SNAPSHOT {model}: {snapshot_path}")

if not gate_ok:
    log("STEP0_HARD_STOP root ground truth was not clean; stop before Step1")
    sys.exit(10)

log("STEP0_PASS ground truth clean and artifact snapshots ready")
PY
step0_ec=$?
if [ "$step0_ec" -ne 0 ]; then
  log "HARD_STOP step0 exit=${step0_ec}"
  exit "$step0_ec"
fi

log "STEP1 verify RQ3 classifier primary source"
python3 - <<'PY' "$ARTIFACT_ROOT/RQ3_Repair/classify_faulty_models.py" "$SUMMARY_LOG"
import sys
from pathlib import Path

path = Path(sys.argv[1])
summary_log = Path(sys.argv[2])
text = path.read_text(encoding="utf-8")
ok = (
    "def run_check_one(" in text
    and '"validation": "check_one"' in text
    and "testsuite_oracle_code_type" in text
    and "pred_equiv_code_type" in text
)
msg = "STEP1_PASS classify_faulty_models.py uses check-one primary with diagnostics" if ok else "STEP1_FAIL classifier source does not look patched"
print(msg)
with summary_log.open("a", encoding="utf-8") as f:
    f.write(msg + "\n")
sys.exit(0 if ok else 11)
PY
step1_ec=$?
if [ "$step1_ec" -ne 0 ]; then
  log "HARD_STOP step1 exit=${step1_ec}"
  exit "$step1_ec"
fi

log "STEP2 run classification for gate"
for model in "${MODELS[@]}"; do
  run_logged \
    "STEP2_CLASSIFY_${model}" \
    "$RUN_DIR/step2_classify_${model}.log" \
    python3 -u RQ3_Repair/classify_faulty_models.py \
      --info-root "result/Gemini/RQ3_Repair/FaultyRewrite/${model}/ARepair_FaultyRewrite"
  ec=$?
  if [ "$ec" -ne 0 ]; then
    log "STEP2_CLASSIFY_WARN ${model} exit=${ec}"
  fi
done

python3 - <<'PY' "$ARTIFACT_ROOT" "$GROUND_TRUTH_DIR" "$SUMMARY_LOG"
import json
import shutil
import sys
from pathlib import Path

artifact = Path(sys.argv[1])
snapshot_dir = Path(sys.argv[2])
summary_log = Path(sys.argv[3])
drift_cases = {
    "gemini-3-flash-preview": ["student_Sorted_llm_8"],
    "gemini-3.1-flash-lite-preview": [
        "dll_ConsistentPreAndNxt_llm_10",
        "dll_ConsistentPreAndNxt_llm_3",
        "dll_ConsistentPreAndNxt_llm_4",
        "dll_ConsistentPreAndNxt_llm_5",
        "dll_ConsistentPreAndNxt_llm_6",
        "dll_ConsistentPreAndNxt_llm_7",
        "dll_ConsistentPreAndNxt_llm_8",
        "dll_ConsistentPreAndNxt_llm_9",
        "farmer_crossRiver_llm_8",
        "farmer_crossRiver_llm_9",
        "student_Contains_llm_10",
        "student_Contains_llm_3",
        "student_Contains_llm_4",
        "student_Contains_llm_5",
        "student_Contains_llm_6",
        "student_Contains_llm_7",
        "student_Contains_llm_9",
        "student_Sorted_llm_4",
        "student_Sorted_llm_6",
        "student_Sorted_llm_8",
    ],
}

def log(msg: str) -> None:
    print(msg)
    with summary_log.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def load_results(path: Path) -> dict:
    return {item.get("unique_id"): item for item in json.loads(path.read_text(encoding="utf-8")).get("results", [])}

failures = []
checked = 0
for model, uids in drift_cases.items():
    snapshot = load_results(snapshot_dir / f"{model}__classification_ground_truth.json")
    current_path = artifact / "result/Gemini/RQ3_Repair/FaultyRewrite" / model / "ARepair_FaultyRewrite/classification.json"
    current = load_results(current_path)
    for uid in uids:
        expected = snapshot.get(uid, {}).get("result")
        actual = current.get(uid, {}).get("result")
        checked += 1
        if expected != actual:
            failures.append((model, uid, expected, actual))

if failures:
    for model, uid, expected, actual in failures:
        log(f"STEP2_GATE_FAIL {model} {uid}: expected={expected} actual={actual}")
    # Restore clean snapshots before stopping, so artifact data is not left in a failed gate state.
    for snap in snapshot_dir.glob("*__classification_ground_truth.json"):
        model = snap.name.split("__", 1)[0]
        dest = artifact / "result/Gemini/RQ3_Repair/FaultyRewrite" / model / "ARepair_FaultyRewrite/classification.json"
        shutil.copy2(snap, dest)
    log(f"STEP2_HARD_STOP checked={checked} matched={checked - len(failures)}")
    sys.exit(20)

log(f"STEP2_PASS 21-case gate matched={checked}/{checked}")
PY
step2_ec=$?
if [ "$step2_ec" -ne 0 ]; then
  log "HARD_STOP step2 exit=${step2_ec}"
  exit "$step2_ec"
fi

log "STEP3 full classification comparison against internal snapshots"
python3 - <<'PY' "$ARTIFACT_ROOT" "$GROUND_TRUTH_DIR" "$SUMMARY_LOG" "$RUN_DIR/step3_full_classification_comparison.csv"
import csv
import json
import sys
from pathlib import Path

artifact = Path(sys.argv[1])
snapshot_dir = Path(sys.argv[2])
summary_log = Path(sys.argv[3])
csv_path = Path(sys.argv[4])
models = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
]

def log(msg: str) -> None:
    print(msg)
    with summary_log.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def load_results(path: Path) -> dict:
    return {item.get("unique_id"): item for item in json.loads(path.read_text(encoding="utf-8")).get("results", [])}

rows = []
total = 0
matches = 0
for model in models:
    snapshot = load_results(snapshot_dir / f"{model}__classification_ground_truth.json")
    current = load_results(
        artifact / "result/Gemini/RQ3_Repair/FaultyRewrite" / model / "ARepair_FaultyRewrite/classification.json"
    )
    for uid in sorted(set(snapshot) | set(current)):
        expected = snapshot.get(uid, {}).get("result", "MISSING")
        actual = current.get(uid, {}).get("result", "MISSING")
        match = expected == actual
        total += 1
        matches += int(match)
        if not match:
            rows.append({"model": model, "unique_id": uid, "expected": expected, "actual": actual})

with csv_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=["model", "unique_id", "expected", "actual"])
    writer.writeheader()
    writer.writerows(rows)

log(f"STEP3_RESULT full_classification matched={matches}/{total} mismatches={len(rows)} csv={csv_path}")
PY

log "STEP4 rerun RQ3 repair with fixed classification"
for model in "${MODELS[@]}"; do
  run_logged \
    "STEP4_RQ3_REPAIR_${model}" \
    "$RUN_DIR/step4_rq3_repair_${model}.log" \
    env PYTHON=python3 TIMEOUT="${TIMEOUT:-600}" \
      bash RQ3_Repair/run_faulty_rewrite_pipeline.sh \
        --model "$model" \
        --out-root "result/Gemini/RQ3_Repair/FaultyRewrite/${model}/ARepair_FaultyRewrite" \
        --skip-llm \
        --run-arepair
  ec=$?
  if [ "$ec" -ne 0 ]; then
    log "STEP4_WARN ${model} exit=${ec}"
  fi
done

python3 - <<'PY' "$ARTIFACT_ROOT" "$SUMMARY_LOG"
import json
import sys
from pathlib import Path
from collections import Counter

artifact = Path(sys.argv[1])
summary_log = Path(sys.argv[2])
models = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
]

def log(msg: str) -> None:
    print(msg)
    with summary_log.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

for model in models:
    root = artifact / "result/Gemini/RQ3_Repair/FaultyRewrite" / model / "ARepair_FaultyRewrite"
    cls = json.loads((root / "classification.json").read_text(encoding="utf-8"))["results"]
    llm_counts = Counter(item["result"] for item in cls if item.get("kind") == "llm")
    orig_counts = Counter(item["result"] for item in cls if item.get("kind") == "original")
    llm_rep = json.loads((root / "RepairResultsLLM/repair_results.json").read_text(encoding="utf-8"))
    orig_rep = json.loads((root / "RepairResultsOriginal/repair_results.json").read_text(encoding="utf-8"))
    llm_success = sum(1 for item in llm_rep if item.get("status") in ("SUCCESS", "PARTIAL"))
    orig_success = sum(1 for item in orig_rep if item.get("status") in ("SUCCESS", "PARTIAL"))
    log(
        f"STEP4_COUNTS {model}: original_sem={orig_counts.get('Sem', 0)} "
        f"llm_sem={llm_counts.get('Sem', 0)} orig_success={orig_success} llm_success={llm_success}"
    )
PY

log "STEP5 RQ2 Docker A/B for dll_ConsistentPreAndNxt_5"
mkdir -p "$AB_DIR/current" "$AB_DIR/top3" "$AB_DIR/source"
cp "$ARTIFACT_ROOT/ARepair/src/main/java/patcher/Patcher.java" "$AB_DIR/source/Patcher_current.java"
if [ -f "$REPO_ROOT/ARepair/src/main/java/patcher/Patcher.java" ]; then
  cp "$REPO_ROOT/ARepair/src/main/java/patcher/Patcher.java" "$AB_DIR/source/Patcher_top3_from_root.java"
else
  log "STEP5_WARN root Patcher.java missing; top3 A/B cannot run"
fi

python3 - <<'PY' "$ARTIFACT_ROOT" "$AB_DIR/repair_info_single.json"
import json
import sys
from pathlib import Path

artifact = Path(sys.argv[1])
out = Path(sys.argv[2])
info_path = artifact / "result/Gemini/RQ2_Validation/A2A/gemini-3.1-flash-lite-preview/NoTest/WrongForRepair/repair_info.json"
item = next(
    dict(x)
    for x in json.loads(info_path.read_text(encoding="utf-8"))
    if x.get("unique_id") == "dll_ConsistentPreAndNxt_5"
)
item["model_path"] = "result/Gemini/RQ2_Validation/A2A/gemini-3.1-flash-lite-preview/NoTest/WrongForRepair/dll_ConsistentPreAndNxt_5.als"
out.write_text(json.dumps([item], indent=2), encoding="utf-8")
print(out)
PY

run_ab_variant() {
  local variant="$1"
  local out_dir_rel="logs/orchestration/rq3_oracle_fix_rq2_ab_${RUN_ID}/rq2_ab_dll_ConsistentPreAndNxt_5/${variant}"
  compose_cmd -f docker-compose.arepair.yml run --rm arepair bash -lc \
    "set -e; cd /workspace; cd ARepair && ./arepair.sh --build && cd /workspace; REPAIR_INFO_JSON=/workspace/logs/orchestration/rq3_oracle_fix_rq2_ab_${RUN_ID}/rq2_ab_dll_ConsistentPreAndNxt_5/repair_info_single.json OUTPUT_DIR=/workspace/${out_dir_rel} AREPAIR_EXPORT_REPAIR_SPACE=0 TIMEOUT=${TIMEOUT:-600} python3 -u scripts/arepair/run_arepair.py"
}

run_logged "STEP5_RQ2_AB_CURRENT" "$AB_DIR/current.log" run_ab_variant "current"
current_ec=$?
if [ "$current_ec" -ne 0 ]; then
  log "STEP5_WARN current A/B exit=${current_ec}"
fi

if [ -f "$AB_DIR/source/Patcher_top3_from_root.java" ]; then
  cp "$AB_DIR/source/Patcher_top3_from_root.java" "$ARTIFACT_ROOT/ARepair/src/main/java/patcher/Patcher.java"
  run_logged "STEP5_RQ2_AB_TOP3" "$AB_DIR/top3.log" run_ab_variant "top3"
  top3_ec=$?
  if [ "$top3_ec" -ne 0 ]; then
    log "STEP5_WARN top3 A/B exit=${top3_ec}"
  fi
else
  top3_ec=99
fi

python3 - <<'PY' "$AB_DIR" "$SUMMARY_LOG"
import json
import sys
from pathlib import Path

ab_dir = Path(sys.argv[1])
summary_log = Path(sys.argv[2])

def log(msg: str) -> None:
    print(msg)
    with summary_log.open("a", encoding="utf-8") as f:
        f.write(msg + "\n")

def status(variant: str) -> str:
    path = ab_dir / variant / "repair_results.json"
    if not path.is_file():
        return "MISSING"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not data:
        return "EMPTY"
    return data[0].get("status", "UNKNOWN")

current = status("current")
top3 = status("top3")
log(f"STEP5_RESULT current={current} top3={top3}")
if current == "SUCCESS" and top3 == "FAILED":
    log("STEP5_DECISION keep_top3_logging=true")
elif current == "SUCCESS" and top3 == "SUCCESS":
    log("STEP5_DECISION keep_top3_logging=false reason=both_success_run_to_run_or_arepair_behavior")
else:
    log("STEP5_DECISION keep_top3_logging=false reason=no_evidence_top3_restores_legacy_failure")
PY

if grep -F "STEP5_DECISION keep_top3_logging=true" "$SUMMARY_LOG" >/dev/null 2>&1; then
  if [ -f "$AB_DIR/source/Patcher_top3_from_root.java" ]; then
    cp "$AB_DIR/source/Patcher_top3_from_root.java" "$ARTIFACT_ROOT/ARepair/src/main/java/patcher/Patcher.java"
    log "STEP5_APPLIED restored top3 Patcher.java"
  fi
else
  cp "$AB_DIR/source/Patcher_current.java" "$ARTIFACT_ROOT/ARepair/src/main/java/patcher/Patcher.java"
  log "STEP5_APPLIED restored current no-top3 Patcher.java"
fi

log "STEP6 regenerate paper/artifact diff"
run_logged \
  "STEP6_DIFF_COMPARE" \
  "$RUN_DIR/step6_compare_paper_artifact.log" \
  python3 scripts/compare_paper_artifact.py
diff_ec=$?
if [ "$diff_ec" -ne 0 ]; then
  log "STEP6_WARN diff exit=${diff_ec}"
fi

{
  echo "RUN_ID=$RUN_ID"
  echo "FINISH=$(date)"
  echo "MASTER_LOG=$MASTER_LOG"
  echo "SUMMARY_LOG=$SUMMARY_LOG"
  echo "RUN_DIR=$RUN_DIR"
  echo "DIFF_LOG=$RUN_DIR/step6_compare_paper_artifact.log"
  echo "DIFF_SUMMARY=$ORCH_DIR/paper_artifact_diff_latest_summary.json"
} > "$DONE_MARKER"

log "ALL_DONE marker=${DONE_MARKER}"
