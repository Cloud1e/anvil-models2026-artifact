#!/bin/bash

# Complete workflow to run ARepair on Wrong predicates
# 1. Extract Wrong predicates
# 2. Run ARepair
# 3. Generate summary with Repairable column

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ARTIFACT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PROJECT_DIR="$ARTIFACT_ROOT"

cd "$PROJECT_DIR"

echo "=== Step 1: Extract Wrong predicates ==="
python "$ARTIFACT_ROOT/scripts/arepair/extract_wrong_predicates.py"

echo -e "\n=== Step 2: Build ARepair (if needed) ==="
cd ARepair
if [ ! -d "target" ]; then
    echo "Building ARepair..."
    ./arepair.sh --build
fi
cd ..

echo -e "\n=== Step 3: Run ARepair on Wrong predicates ==="
python "$ARTIFACT_ROOT/scripts/arepair/run_arepair.py"

echo -e "\n=== Step 4: Generate summary with Repairable column ==="
python "$ARTIFACT_ROOT/scripts/arepair/generate_repairable_summary.py"

echo -e "\n=== Done ==="
