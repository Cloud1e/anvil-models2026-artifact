#!/bin/bash

# Script to run ARepair on extracted Wrong predicates
# Usage: ./run_arepair.sh <repair_info.json> <output_dir>

set -e

REPAIR_INFO_JSON="${1:-/workspace/result/Gemini/ARepair/WrongForRepair/repair_info.json}"
OUTPUT_DIR="${2:-/workspace/result/Gemini/ARepair/RepairResults}"
AREPAIR_DIR="/workspace/ARepair"

# Default ARepair settings (can be overridden)
SCOPE="${SCOPE:-3}"
MIN_COST="${MIN_COST:-1}"
SEARCH_STRATEGY="${SEARCH_STRATEGY:-base-choice}"
MAX_TRY_PER_HOLE="${MAX_TRY_PER_HOLE:-100}"

mkdir -p "$OUTPUT_DIR"

echo "Running ARepair on Wrong predicates..."
echo "Repair info: $REPAIR_INFO_JSON"
echo "Output directory: $OUTPUT_DIR"

# Parse JSON and run ARepair for each predicate (python3 in Docker image)
python3 << EOF
import json
import os
import subprocess
import sys

with open('$REPAIR_INFO_JSON', 'r') as f:
    repair_info = json.load(f)

results = []

for item in repair_info:
    unique_id = item['unique_id']
    model_path = item['model_path']
    test_suite_path = item['test_suite_path']
    
    print(f"\nProcessing {unique_id}...")
    print(f"  Model: {model_path}")
    print(f"  Test suite: {test_suite_path}")
    
    if not os.path.exists(model_path):
        print(f"  ERROR: Model file not found: {model_path}")
        results.append({
            'unique_id': unique_id,
            'status': 'ERROR',
            'message': 'Model file not found'
        })
        continue
    
    if not os.path.exists(test_suite_path):
        print(f"  ERROR: Test suite not found: {test_suite_path}")
        results.append({
            'unique_id': unique_id,
            'status': 'ERROR',
            'message': 'Test suite not found'
        })
        continue
    
    # Run ARepair
    output_file = os.path.join('$OUTPUT_DIR', f"{unique_id}.log")
    
    cmd = [
        'bash', '${AREPAIR_DIR}/arepair.sh', '--run',
        '-m', model_path,
        '-t', test_suite_path,
        '-s', '$SCOPE',
        '-c', '$MIN_COST',
        '-g', '$SEARCH_STRATEGY',
        '-h', '$MAX_TRY_PER_HOLE'
    ]
    
    print(f"  Running: {' '.join(cmd)}")
    
    try:
        with open(output_file, 'w') as fout:
            result = subprocess.run(
                cmd,
                stdout=fout,
                stderr=subprocess.STDOUT,
                timeout=300,  # 5 minutes timeout
                cwd='$AREPAIR_DIR'
            )
        
        # Check if repair was successful
        # ARepair stores fixed model at .hidden/fix.als
        fixed_model_path = os.path.join('$AREPAIR_DIR', '.hidden', 'fix.als')
        
        if os.path.exists(fixed_model_path) and result.returncode == 0:
            # Try to check if all tests pass by parsing the output
            with open(output_file, 'r') as f:
                output = f.read()
                if 'all tests pass' in output.lower() or 'fixed model' in output.lower():
                    status = 'SUCCESS'
                else:
                    status = 'PARTIAL' if 'partially fixed' in output.lower() else 'FAILED'
        else:
            status = 'FAILED'
        
        results.append({
            'unique_id': unique_id,
            'status': status,
            'return_code': result.returncode,
            'output_file': output_file,
            'fixed_model_path': fixed_model_path if os.path.exists(fixed_model_path) else None
        })
        
        print(f"  Status: {status}")
        
    except subprocess.TimeoutExpired:
        print(f"  ERROR: Timeout")
        results.append({
            'unique_id': unique_id,
            'status': 'TIMEOUT'
        })
    except Exception as e:
        print(f"  ERROR: {str(e)}")
        results.append({
            'unique_id': unique_id,
            'status': 'ERROR',
            'message': str(e)
        })

# Save results
results_file = os.path.join('$OUTPUT_DIR', 'repair_results.json')
with open(results_file, 'w') as f:
    json.dump(results, f, indent=2)

print(f"\n=== Summary ===")
total = len(results)
success = sum(1 for r in results if r['status'] == 'SUCCESS')
failed = sum(1 for r in results if r['status'] == 'FAILED')
partial = sum(1 for r in results if r['status'] == 'PARTIAL')
errors = sum(1 for r in results if r['status'] in ['ERROR', 'TIMEOUT'])

print(f"Total: {total}")
print(f"Success: {success}")
print(f"Partial: {partial}")
print(f"Failed: {failed}")
print(f"Errors: {errors}")
print(f"\nResults saved to: {results_file}")
EOF

echo "Done!"
