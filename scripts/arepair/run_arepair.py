#!/usr/bin/env python
"""
Run ARepair on extracted Wrong predicates and collect results.

Usage:
  python run_arepair.py                    # original test suites -> repair_results.json
  python run_arepair.py --extended         # use combined_tests.als when available -> repair_results_extended.json
  python run_arepair.py --test-suite-80    # use 80% test suite -> repair_results_80.json
  python run_arepair.py --extended --filter arr   # same, but only model_name==arr (e.g. REPAIR_FILTER=arr)
"""

import argparse
import json
import os
import subprocess
import sys
import threading
from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = _artifact_repo_root()

# Default paths (can be overridden by environment variables)
REPAIR_INFO_JSON = os.getenv('REPAIR_INFO_JSON', str(PROJECT_DIR / 'result/Gemini/ARepair/WrongForRepair/repair_info.json'))
OUTPUT_DIR = os.getenv('OUTPUT_DIR', str(PROJECT_DIR / 'result/Gemini/ARepair/RepairResults'))
AREPAIR_DIR = os.getenv('AREPAIR_DIR', str(PROJECT_DIR / 'ARepair'))
TESTGEN_TESTS_DIR = PROJECT_DIR / 'testgen/tests'

# Default ARepair settings (can be overridden by environment variables)
SCOPE = os.getenv('SCOPE', '3')
MIN_COST = os.getenv('MIN_COST', '1')
SEARCH_STRATEGY = os.getenv('SEARCH_STRATEGY', 'base-choice')
MAX_TRY_PER_HOLE = os.getenv('MAX_TRY_PER_HOLE', '50')
# Per-predicate timeout (seconds). Override with env TIMEOUT=300 etc. if needed.
TIMEOUT = int(os.getenv('TIMEOUT', '600'))
# When truthy (default), pass ARepair -r so each run writes <case>.repair_space.jsonl next to the .log (holes + search space without relying on DEBUG logs).
_EXPORT_RS = os.getenv('AREPAIR_EXPORT_REPAIR_SPACE', '1').strip().lower() not in (
    '0', 'false', 'no', 'off',
)


def parse_result_file(result_path, is_single_predicate_model=False):
    """Parse a result file and extract predicates with their status."""
    predicates = []
    if not result_path.exists():
        return predicates
    
    with open(result_path, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("Total:") or line.startswith("Unique:"):
            i += 1
            continue
        
        if is_single_predicate_model:
            if i + 1 < len(lines) and lines[i + 1].strip() in ["Correct", "Syntax Error", "Wrong"]:
                predicates.append({
                    'name': None,
                    'body': line,
                    'status': lines[i + 1].strip()
                })
                i += 1
        else:
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    predicate_name = parts[0].strip()
                    body = parts[1].strip()
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip()
                        if next_line in ["Correct", "Syntax Error", "Wrong"]:
                            predicates.append({
                                'name': predicate_name,
                                'body': body,
                                'status': next_line
                            })
                            i += 1
            else:
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line in ["Correct", "Syntax Error", "Wrong"]:
                        predicates.append({
                            'name': None,
                            'body': line,
                            'status': next_line
                        })
                        i += 1
        i += 1
    
    return predicates

def has_both_wrong_and_correct(model_name, predicate_name):
    """Check if model-predicate combination has both Wrong and Correct results.
    
    Extended mode should only be used when both Wrong and Correct exist,
    because extended tests are generated from Correct examples to repair Wrong ones.
    """
    RESULTS_DIR = PROJECT_DIR / "result/Gemini/ARepair/Alloy"
    result_file = RESULTS_DIR / f"{model_name}.txt"
    
    if not result_file.exists():
        return False
    
    # Determine if this is a single-predicate model
    MODEL_PREDICATES = {
        "arr": ["NoConflict"],
        "balancedBST": ["Balanced", "HasAtMostOneChild", "Sorted"],
        "bempl": ["CanEnter"],
        "cd": ["Acyclic", "AllExtObject", "ClassHierarchy", "ObjectNoExt"],
        "dll": ["ConsistentPreAndNxt", "Sorted", "UniqueElem"],
        "farmer": ["crossRiver", "solvePuzzle"],
        "grade": ["PolicyAllowsGrading"],
        "other": ["CanEnter"],
        "student": ["Contains", "Count", "Loop", "Sorted"],
    }
    
    predicates = MODEL_PREDICATES.get(model_name, [])
    is_single_predicate_model = len(predicates) == 1
    
    all_predicates = parse_result_file(result_file, is_single_predicate_model=is_single_predicate_model)
    
    has_wrong = False
    has_correct = False
    
    has_named_predicates = any(p['name'] is not None for p in all_predicates)
    
    if has_named_predicates:
        # Multi-predicate model
        for pred_data in all_predicates:
            if pred_data['name'] == predicate_name:
                if pred_data['status'] == 'Wrong':
                    has_wrong = True
                elif pred_data['status'] == 'Correct':
                    has_correct = True
    else:
        # Single-predicate model
        for pred_data in all_predicates:
            if pred_data['status'] == 'Wrong':
                has_wrong = True
            elif pred_data['status'] == 'Correct':
                has_correct = True
    
    return has_wrong and has_correct

def get_extended_test_suite(model_name, predicate_name):
    """If testgen/tests/<model>_<pred>/combined_tests.als exists, return its path; else None."""
    combined = TESTGEN_TESTS_DIR / f"{model_name}_{predicate_name}" / "combined_tests.als"
    if combined.exists():
        return str(combined.resolve())
    return None

def get_test_suite_80_path(model_name):
    """Get path to 80% test suite if it exists."""
    test_suite_80 = PROJECT_DIR / "ARepair" / "experiments" / "test-suite-80" / f"{model_name}.als"
    if test_suite_80.exists():
        return str(test_suite_80.resolve())
    return None


def run_arepair(unique_id, model_path, test_suite_path, output_dir, test_mode='original'):
    """Run ARepair on a single model and return results.
    
    Args:
        test_mode: 'original', 'extended', or '80'
    """
    if not os.path.isabs(model_path):
        model_path = str(PROJECT_DIR / model_path)
    if not os.path.isabs(test_suite_path):
        test_suite_path = str(PROJECT_DIR / test_suite_path)

    print(f"\nProcessing {unique_id}...")
    print(f"  Model: {model_path}")
    print(f"  Test suite: {test_suite_path}")

    if not os.path.exists(model_path):
        print(f"  ERROR: Model file not found: {model_path}")
        return {'unique_id': unique_id, 'status': 'ERROR', 'message': 'Model file not found'}

    if not os.path.exists(test_suite_path):
        print(f"  ERROR: Test suite not found: {test_suite_path}")
        return {'unique_id': unique_id, 'status': 'ERROR', 'message': 'Test suite not found'}

    log_suffix = f'_{test_mode}' if test_mode != 'original' else ''
    output_file = os.path.join(output_dir, f"{unique_id}{log_suffix}.log")
    repair_space_file = os.path.join(output_dir, f"{unique_id}{log_suffix}.repair_space.jsonl")

    model_path_abs = os.path.abspath(model_path)
    test_suite_path_abs = os.path.abspath(test_suite_path)
    
    # Create .hidden directory if it doesn't exist (ARepair needs this)
    hidden_dir = os.path.join(AREPAIR_DIR, '.hidden')
    os.makedirs(hidden_dir, exist_ok=True)
    
    cmd = [
        'bash', os.path.join(AREPAIR_DIR, 'arepair.sh'), '--run',
        '-m', model_path_abs,
        '-t', test_suite_path_abs,
        '-s', SCOPE,
        '-c', MIN_COST,
        '-g', SEARCH_STRATEGY,
        '-h', MAX_TRY_PER_HOLE,
    ]
    if _EXPORT_RS:
        cmd.extend(['-r', os.path.abspath(repair_space_file)])
    
    print(f"  Running: {' '.join(cmd)}")
    print(f"  Model (abs): {model_path_abs}")
    print(f"  Test suite (abs): {test_suite_path_abs}")
    
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=AREPAIR_DIR,
            universal_newlines=True,
            bufsize=1,
        )
        timed_out = False
        with open(output_file, 'w') as fout:
            def tee():
                try:
                    for line in proc.stdout:
                        fout.write(line)
                        fout.flush()
                        print(line, end='', flush=True)
                except (ValueError, OSError):
                    pass  # fout closed on timeout path
            reader = threading.Thread(target=tee, daemon=True)
            reader.start()
            try:
                returncode = proc.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                timed_out = True
                proc.kill()
                if proc.stdout:
                    try:
                        proc.stdout.close()
                    except Exception:
                        pass
                proc.wait()
                returncode = -1
            reader.join(timeout=5.0)
        if timed_out:
            print(f"  ERROR: Timeout after {TIMEOUT} seconds")
            return {'unique_id': unique_id, 'status': 'TIMEOUT'}
        result = type('Result', (), {'returncode': returncode})()

        # Check if repair was successful
        # ARepair stores fixed model at .hidden/fix.als
        fixed_model_path = os.path.join(AREPAIR_DIR, '.hidden', 'fix.als')
        
        # Parse output to determine status (already in file)
        with open(output_file, 'r') as f:
            output = f.read()
            
        # Check for success indicators
        if result.returncode == 0 and os.path.exists(fixed_model_path):
            if 'all tests pass' in output.lower() or 'fixed model' in output.lower() or 'Solution found' in output:
                status = 'SUCCESS'
            elif 'partially fixed' in output.lower():
                status = 'PARTIAL'
            else:
                status = 'FAILED'
        else:
            status = 'FAILED'
        
        return {
            'unique_id': unique_id,
            'status': status,
            'return_code': result.returncode,
            'output_file': output_file,
            'fixed_model_path': fixed_model_path if os.path.exists(fixed_model_path) else None
        }
    except Exception as e:
        print(f"  ERROR: {str(e)}")
        return {
            'unique_id': unique_id,
            'status': 'ERROR',
            'message': str(e)
        }

def main():
    parser = argparse.ArgumentParser(description='Run ARepair on Wrong predicates')
    parser.add_argument('--extended', action='store_true', help='Use testgen/tests/<model_pred>/combined_tests.als when available; output repair_results_extended.json')
    parser.add_argument('--test-suite-80', action='store_true', help='Use test-suite-80 (80%% of original tests); output repair_results_80.json')
    parser.add_argument('--filter', type=str, default=os.getenv('REPAIR_FILTER', ''), metavar='MODEL', help='Only process model_name==MODEL (e.g. arr)')
    args = parser.parse_args()

    # Determine test mode
    if args.test_suite_80:
        test_mode = '80'
    elif args.extended:
        test_mode = 'extended'
    else:
        test_mode = 'original'
    
    filter_model = (args.filter or '').strip()

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print("Running ARepair on Wrong predicates...")
    if test_mode == 'extended':
        print("Mode: EXTENDED (combined_tests.als when available)")
    elif test_mode == '80':
        print("Mode: 80% (test-suite-80)")
    else:
        print("Mode: ORIGINAL (experiments/test-suite)")
    print(f"Repair info: {REPAIR_INFO_JSON}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"ARepair directory: {AREPAIR_DIR}")

    with open(REPAIR_INFO_JSON, 'r') as f:
        repair_info = json.load(f)

    if filter_model:
        repair_info = [x for x in repair_info if x.get('model_name') == filter_model]
        print('Filter: model_name == "{}" -> {} predicates'.format(filter_model, len(repair_info)))

    print(f"\nTotal predicates to repair: {len(repair_info)}")

    results = []
    for i, item in enumerate(repair_info, 1):
        test_suite_path = item['test_suite_path']
        
        skip_reason = None
        if test_mode == 'extended':
            # Extended mode requires both Wrong and Correct results
            # because extended tests are generated from Correct examples to repair Wrong ones
            if has_both_wrong_and_correct(item['model_name'], item['predicate_name']):
                extended_path = get_extended_test_suite(item['model_name'], item['predicate_name'])
                if extended_path:
                    test_suite_path = extended_path
                    print(f"\n[{i}/{len(repair_info)}] {item['unique_id']} -> extended", end="")
                else:
                    # Has both wrong+correct but no extended tests found - skip
                    skip_reason = 'no extended tests found'
                    print(f"\n[{i}/{len(repair_info)}] {item['unique_id']} -> SKIPPED (no extended tests found)", end="")
            else:
                # Doesn't have both wrong+correct - skip
                skip_reason = 'no both wrong+correct'
                print(f"\n[{i}/{len(repair_info)}] {item['unique_id']} -> SKIPPED (no both wrong+correct)", end="")
        elif test_mode == '80':
            test_suite_80_path = get_test_suite_80_path(item['model_name'])
            if test_suite_80_path:
                test_suite_path = test_suite_80_path
                print(f"\n[{i}/{len(repair_info)}] {item['unique_id']} -> 80%", end="")
            else:
                test_suite_path = str((PROJECT_DIR / test_suite_path).resolve())
                print(f"\n[{i}/{len(repair_info)}] {item['unique_id']} -> original (no 80% found)", end="")
        else:
            test_suite_path = str((PROJECT_DIR / test_suite_path).resolve())
            print(f"\n[{i}/{len(repair_info)}] {item['unique_id']}", end="")

        if skip_reason:
            # Skip running ARepair, mark as NA
            result = {
                'unique_id': item['unique_id'],
                'status': 'NA',
                'skip_reason': skip_reason,
                'output_file': None,
                'fixed_model_path': None
            }
        else:
            result = run_arepair(
                item['unique_id'],
                item['model_path'],
                test_suite_path,
                OUTPUT_DIR,
                test_mode=test_mode
            )
        results.append(result)

        # Running stats after each case
        n_success = sum(1 for r in results if r.get('status') == 'SUCCESS')
        n_partial = sum(1 for r in results if r.get('status') == 'PARTIAL')
        n_failed = sum(1 for r in results if r.get('status') == 'FAILED')
        n_errors = sum(1 for r in results if r.get('status') in ('ERROR', 'TIMEOUT'))
        n_na = sum(1 for r in results if r.get('status') == 'NA')
        status_display = result.get('status', '?')
        if status_display == 'NA':
            status_display = f"NA ({result.get('skip_reason', 'unknown')})"
        print(f"  -> {status_display} | Running: Success={n_success}, Failed={n_failed}, Partial={n_partial}, Errors={n_errors}, NA={n_na} ({i}/{len(repair_info)})")

        if i % 10 == 0:
            if test_mode == 'extended':
                mid_name = 'repair_results_extended_intermediate.json'
            elif test_mode == '80':
                mid_name = 'repair_results_80_intermediate.json'
            else:
                mid_name = 'repair_results_intermediate.json'
            mid_file = os.path.join(OUTPUT_DIR, mid_name)
            with open(mid_file, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\n  (Progress saved to {mid_file})")

    if test_mode == 'extended':
        results_file = os.path.join(OUTPUT_DIR, 'repair_results_extended.json')
    elif test_mode == '80':
        results_file = os.path.join(OUTPUT_DIR, 'repair_results_80.json')
    else:
        results_file = os.path.join(OUTPUT_DIR, 'repair_results.json')
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    print(f"\n{'='*60}")
    print("=== Summary ===")
    total = len(results)
    success = sum(1 for r in results if r['status'] == 'SUCCESS')
    partial = sum(1 for r in results if r['status'] == 'PARTIAL')
    failed = sum(1 for r in results if r['status'] == 'FAILED')
    errors = sum(1 for r in results if r['status'] in ['ERROR', 'TIMEOUT'])
    na = sum(1 for r in results if r['status'] == 'NA')
    print(f"Total: {total}  Success: {success}  Partial: {partial}  Failed: {failed}  Errors: {errors}  NA: {na}")
    print(f"Results saved to: {results_file}")
    print(f"{'='*60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
