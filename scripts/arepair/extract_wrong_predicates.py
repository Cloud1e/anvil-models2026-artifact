#!/usr/bin/env python
"""
Extract Wrong (and optionally Syntax Error) predicates from Alloy result files and prepare them for ARepair tool.

Usage:
  python extract_wrong_predicates.py
      # default: result/Gemini/ARepair/Alloy -> result/Gemini/ARepair/WrongForRepair
  python extract_wrong_predicates.py --alloy-dir result/Gemini/ARepairNoTest/Alloy --output-dir result/Gemini/ARepairNoTest/WrongForRepair
      # for NoTest: extract from NoTest Alloy into NoTest WrongForRepair
  python extract_wrong_predicates.py --include-se
      # also include Syntax Error (in addition to Wrong)
"""

import argparse
import json
import re
from pathlib import Path
from typing import Optional

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



# Base directories
BASE_DIR = _artifact_repo_root()
RESULTS_DIR = BASE_DIR / "result/Gemini/ARepair/Alloy"
ALL_MODELS_DIR = BASE_DIR / "ARepair/experiments/models"
REALBUGS_DIR = BASE_DIR / "ARepair/experiments/realbugs"
TEST_SUITE_DIR = BASE_DIR / "ARepair/experiments/test-suite"
OUTPUT_DIR = BASE_DIR / "result/Gemini/ARepair/WrongForRepair"


def _get_base_model_content(model_name: str) -> Optional[str]:
    """Read base model (sigs + facts). Prefer models/; fallback to realbugs/<model>1.als if models/ has no sigs."""
    path = ALL_MODELS_DIR / f"{model_name}.als"
    if path.exists():
        content = path.read_text(encoding="utf-8", errors="ignore")
        if "sig " in content or "one sig " in content:
            return content
    fallback = REALBUGS_DIR / f"{model_name}1.als"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8", errors="ignore")
    return None

# Model to predicate mapping (from your table)
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

def parse_result_file(result_file, is_single_predicate_model=False):
    """Parse a result file and extract predicates with their status.
    
    Args:
        result_file: Path to the result file
        is_single_predicate_model: If True, treat as single-predicate model where
                                   all entries belong to one predicate (don't use ':'
                                   to extract predicate names)
    """
    predicates = []
    
    with open(result_file, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        # Skip summary lines (Total:, Unique:), but NOT status lines
        if line.startswith('Total:') or line.startswith('Unique:'):
            i += 1
            continue
        
        # Skip empty lines
        if not line:
            i += 1
            continue
        
        if is_single_predicate_model:
            # Single-predicate model: treat whole line as body, no predicate name
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line in ["Correct", "Syntax Error", "Wrong"]:
                    predicates.append({
                        'name': None,
                        'body': line,
                        'status': next_line
                    })
                    i += 1
        else:
            # Multi-predicate model: check if line contains predicate name (format: "predicateName: body")
            if ':' in line:
                parts = line.split(':', 1)
                if len(parts) == 2:
                    predicate_name = parts[0].strip()
                    body = parts[1].strip()
                    
                    # Check next line for status
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
                # Format without predicate name prefix - treat as body only
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line in ["Correct", "Syntax Error", "Wrong"]:
                        predicates.append({
                            'name': None,  # Will be determined by model
                            'body': line,
                            'status': next_line
                        })
                        i += 1
        i += 1
    
    return predicates

def _pred_pattern(pred_name: str):
    """Regex for an Alloy predicate definition header+body.

    Supports:
      - pred name[...] {...}
      - pred name(...) {...}
      - pred name {...}
    """
    return re.compile(
        r"pred\s+"
        + re.escape(pred_name)
        + r"\s*(?:\[[^\]]*\]|\([^)]*\))?\s*\{",
        re.MULTILINE,
    )


def create_model_with_predicate(model_name, predicate_name, predicate_body):
    """Create a model file with the given predicate body."""
    model_content = _get_base_model_content(model_name)
    if not model_content:
        print(f"Warning: No base model found for {model_name} (tried models/ and realbugs/)")
        return None
    
    # Find the predicate in the original model and replace its body.
    # Use a pattern that handles [], (), or no parameter list, then
    # walk braces to match the full body.
    def match_predicate_with_nested_braces(content, pred_name):
        """Match predicate with nested braces by counting brace depth."""
        header_re = _pred_pattern(pred_name)
        match = header_re.search(content)
        if not match:
            return None, None, None

        start_pos = match.start()
        # Start after the opening brace
        pos = match.end()
        brace_count = 1  # We already saw the opening brace
        
        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        if brace_count == 0:
            return start_pos, pos, match.group(0)
        return None, None, None
    
    # Try to find and replace using brace counting
    start, end, header = match_predicate_with_nested_braces(model_content, predicate_name)

    if start is not None and end is not None:
        # Preserve original header (with parameters), replace body only
        new_predicate = f'{header}\n  {predicate_body}\n}}'
        model_content = model_content[:start] + new_predicate + model_content[end:]
    else:
        # Append new predicate if not found (might be a fact converted to pred)
        # Try to find if it's a fact
        fact_pattern = rf'fact\s+{predicate_name}\s*{{[^}}]*}}'
        if re.search(fact_pattern, model_content):
            # Remove fact and add as predicate
            model_content = re.sub(fact_pattern, '', model_content)

        # Fallback header if we couldn't find original predicate signature
        new_predicate = f'pred {predicate_name}() {{\n  {predicate_body}\n}}'
        
        # Append the predicate before the last run/check command
        if 'run' in model_content or 'check' in model_content:
            # Find the last run/check and insert before it
            lines = model_content.split('\n')
            insert_pos = len(lines)
            for i in range(len(lines) - 1, -1, -1):
                if lines[i].strip().startswith('run') or lines[i].strip().startswith('check'):
                    insert_pos = i
                    break
            lines.insert(insert_pos, new_predicate)
            model_content = '\n'.join(lines)
        else:
            # Append at the end
            model_content += '\n' + new_predicate
    
    return model_content

def main():
    """Main function to extract Wrong (and optionally SE) predicates and prepare models for ARepair."""
    parser = argparse.ArgumentParser(description='Extract Wrong predicates for ARepair')
    parser.add_argument('--alloy-dir', type=str, default=None,
                        help='Directory with model .txt result files (default: result/Gemini/ARepair/Alloy)')
    parser.add_argument('--output-dir', type=str, default=None,
                        help='Output directory for WrongForRepair (default: result/Gemini/ARepair/WrongForRepair)')
    parser.add_argument('--include-se', action='store_true',
                        help='Also include Syntax Error in addition to Wrong')
    parser.add_argument('--bench-models', type=str, default='',
                        help='Comma-separated benchmark names without .txt (e.g. student,cd). '
                             'Only these models are scanned for Wrong/SE; others are skipped.')
    args = parser.parse_args()

    results_dir = (BASE_DIR / args.alloy_dir) if args.alloy_dir else RESULTS_DIR
    output_dir = (BASE_DIR / args.output_dir) if args.output_dir else OUTPUT_DIR
    include_se = args.include_se
    bench_allow = None
    if args.bench_models and args.bench_models.strip():
        bench_allow = {p.strip() for p in args.bench_models.split(',') if p.strip()}

    output_dir.mkdir(parents=True, exist_ok=True)

    wrong_predicates_by_model = {}

    # Parse all result files
    for model_name, predicates in MODEL_PREDICATES.items():
        if bench_allow is not None and model_name not in bench_allow:
            continue
        result_file = results_dir / f"{model_name}.txt"
        
        if not result_file.exists():
            print(f"Warning: Result file {result_file} not found")
            continue
        
        # Determine if this is a single-predicate model
        is_single_predicate_model = len(predicates) == 1
        
        # Parse with appropriate logic
        all_predicates = parse_result_file(result_file, is_single_predicate_model=is_single_predicate_model)
        wrong_predicates = []
        
        # Check if predicates have names or not (single-predicate models like arr)
        has_named_predicates = any(p['name'] is not None for p in all_predicates)
        
        def status_ok(s):
            return s == 'Wrong' or (include_se and s == 'Syntax Error')

        if has_named_predicates:
            # Multi-predicate model (like dll, cd)
            for pred_name in predicates:
                for pred_data in all_predicates:
                    if pred_data['name'] == pred_name and status_ok(pred_data['status']):
                        wrong_predicates.append({
                            'name': pred_name,
                            'body': pred_data['body']
                        })
        else:
            # Single-predicate model (like arr) - all results are for one predicate
            if len(predicates) == 1:
                pred_name = predicates[0]
                for pred_data in all_predicates:
                    if status_ok(pred_data['status']):
                        wrong_predicates.append({
                            'name': pred_name,
                            'body': pred_data['body']
                        })
        
        if wrong_predicates:
            wrong_predicates_by_model[model_name] = wrong_predicates
    
    # Create model files for each wrong predicate
    repair_info = []
    
    for model_name, wrong_preds in wrong_predicates_by_model.items():
        for i, wrong_pred in enumerate(wrong_preds):
            pred_name = wrong_pred['name']
            pred_body = wrong_pred['body']
            
            # Create unique identifier
            unique_id = f"{model_name}_{pred_name}_{i}"
            
            # Create model content
            model_content = create_model_with_predicate(model_name, pred_name, pred_body)
            
            if model_content:
                # Save model file
                model_output_path = output_dir / f"{unique_id}.als"
                with open(model_output_path, 'w') as f:
                    f.write(model_content)
                
                # Get test suite path
                test_suite_path = TEST_SUITE_DIR / f"{model_name}.als"
                # Store relative paths so Docker (/workspace) can resolve them
                model_rel = model_output_path.relative_to(BASE_DIR)
                test_rel = test_suite_path.relative_to(BASE_DIR)

                repair_info.append({
                    'unique_id': unique_id,
                    'model_name': model_name,
                    'predicate_name': pred_name,
                    'model_path': str(model_rel),
                    'test_suite_path': str(test_rel),
                    'predicate_body': pred_body
                })
    
    # Save repair info to JSON for the next script
    repair_info_file = output_dir / "repair_info.json"
    with open(repair_info_file, 'w') as f:
        json.dump(repair_info, f, indent=2)
    
    kind = "Wrong+SE" if include_se else "Wrong"
    print(f"Extracted {len(repair_info)} {kind} predicates for repair")
    print(f"Info saved to {repair_info_file}")
    print(f"Models saved to {output_dir}")
    
    return repair_info

if __name__ == "__main__":
    main()
