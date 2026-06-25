#!/usr/bin/env bash
# Generate repair_info_original.json + repair_info_llm.json under thesis RQ2 dirs **without copying**
# from legacy paths. Uses run_faulty_rewrite.py --dry-run: scans faulty cases and writes JSON only
# (no API). LLM file is [] until you run a full LLM rewrite (run_faulty_rewrite.py without --dry-run).
#
# Usage (repo root):
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/generate_thesis_repair_info.sh gemini-3.1-flash-lite-preview
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/generate_thesis_repair_info.sh all
#
# If you already have models/llm_faulty_models/*.als but repair_info_llm.json was wiped to [],
# rebuild manifests without LLM calls:
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/rebuild_repair_info_llm_thesis_three_models.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python}"
PY="$SCRIPT_DIR/run_faulty_rewrite.py"

run_one() {
  local m="$1"
  local out="result/thesis/RQ2_FaultyRewrite_ARepair/$m"
  echo "=== Generating repair_info JSON -> $out ==="
  mkdir -p "$out"
  "$PYTHON" -u "$PY" --dry-run --model "$m" --out-root "$out"
}

M="${1:?usage: $0 <gemini-...|all>}"

if [[ "$M" == "all" ]]; then
  for m in gemini-3.1-flash-lite-preview gemini-3-flash-preview gemini-3.1-pro-preview; do
    run_one "$m"
  done
else
  run_one "$M"
fi

echo "Done. Run RQ2 classify / full faulty pipeline when ready."
