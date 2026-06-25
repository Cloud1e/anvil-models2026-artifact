#!/bin/bash
# Re-run WithTest evaluation: read result/Gemini/ARepair/responses/, write .../ARepair/Alloy/.
#
# With the subfolder option (arepair.result.subfolder), NoTest uses ARepairNoTest/
# and no longer overwrites ARepair/. Use this script when you have updated WithTest
# responses and want to regenerate ARepair/Alloy/.
#
# Steps:
#   1. Ensure result/Gemini/ARepair/responses/ contains **WithTest** LLM outputs.
#   2. Run this script. Java runs with default subfolder=ARepair; output -> ARepair/Alloy/.
#
# Usage: from project root:
#   bash scripts/with_vs_without_test/english_to_alloy/restore_withtest_alloy.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"
cd "$PROJECT_DIR"

AREPAIR_RESPONSES="$PROJECT_DIR/result/Gemini/ARepair/responses"
if [ ! -d "$AREPAIR_RESPONSES" ] || [ -z "$(ls -A "$AREPAIR_RESPONSES" 2>/dev/null)" ]; then
  echo "Error: No files in $AREPAIR_RESPONSES"
  echo "Put WithTest LLM responses there (e.g. arr.txt, student.txt, ...) then run this script again."
  exit 1
fi

echo "=== Restoring WithTest Alloy results ==="
echo "Using responses from: $AREPAIR_RESPONSES"
echo "Running Java (ProcessARepairResults) -> result/Gemini/ARepair/Alloy/"
# AREPAIR_VALIDATION=testsuite (default, unified thesis) or equivalence. Same as evaluate_withtest_responses.py.
V="${AREPAIR_VALIDATION:-testsuite}"
mvn -q clean compile exec:java -Dexec.mainClass=Example -Darepair.validation="$V"
echo "Done. result/Gemini/ARepair/Alloy/ now contains WithTest evaluation."
