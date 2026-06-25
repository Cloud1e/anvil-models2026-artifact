#!/usr/bin/env bash
# Rebuild repair_info_llm.json from disk for the three thesis Gemini models (see run_thesis_single_rq_three_models.sh).
# Use when models/llm_faulty_models/*.als exist but repair_info_llm.json was [] (e.g. after generate_thesis_repair_info.sh dry-run).
#
# Usage (repo root):
#   bash scripts/thesis/RQ2_FaultyRewrite_ARepair/rebuild_repair_info_llm_thesis_three_models.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python}"
PY="$SCRIPT_DIR/rebuild_repair_info_llm_from_disk.py"

for m in gemini-3.1-flash-lite-preview gemini-3-flash-preview gemini-3.1-pro-preview; do
  echo "=== $m ==="
  "$PYTHON" -u "$PY" --info-root "result/thesis/RQ2_FaultyRewrite_ARepair/$m"
done

echo "Done."
