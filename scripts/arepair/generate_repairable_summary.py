#!/usr/bin/env python
"""
Generate summary table with Repairable column from ARepair results.
"""

import json
import os
import re
from collections import defaultdict
from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



# Base directories
BASE_DIR = _artifact_repo_root()
RESULTS_DIR = BASE_DIR / "result/Gemini/ARepair/Alloy"
REPAIR_RESULTS_DIR = BASE_DIR / "result/Gemini/ARepair/RepairResults"
OUTPUT_DIR = BASE_DIR / "result"

# Model to predicate mapping
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
        
        # Skip summary lines (Total:, Unique:), but NOT status lines (Correct, Syntax Error, Wrong)
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
            # Multi-predicate model: check if line has format "predicateName: body"
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
                # Line without ':' - treat as body only
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

def load_repair_results(mode='original'):
    """Load ARepair results.
    
    Args:
        mode: 'original', 'extended', or '80'
    
    Returns:
        dict: mapping from unique_id -> status (True/False/None)
        - True: repairable (SUCCESS or PARTIAL)
        - False: not repairable (FAILED, ERROR, TIMEOUT)
        - None: NA (skipped in extended mode)
    """
    if mode == 'extended':
        results_file = REPAIR_RESULTS_DIR / "repair_results_extended.json"
    elif mode == '80':
        results_file = REPAIR_RESULTS_DIR / "repair_results_80.json"
    else:
        results_file = REPAIR_RESULTS_DIR / "repair_results.json"
    
    if not results_file.exists():
        print(f"Warning: Repair results file not found: {results_file}")
        return {}
    
    with open(results_file, 'r') as f:
        results = json.load(f)
    
    # Create mapping: unique_id -> status
    repair_map = {}
    for result in results:
        unique_id = result['unique_id']
        status = result['status']
        if status == 'NA':
            # NA means skipped (not applicable in extended mode)
            repair_map[unique_id] = None
        elif status in ['SUCCESS', 'PARTIAL']:
            repair_map[unique_id] = True
        else:
            repair_map[unique_id] = False
    
    return repair_map

def main():
    """Generate summary table with Repairable column."""
    import argparse
    parser = argparse.ArgumentParser(description='Generate repairable summary table')
    parser.add_argument('--mode', choices=['original', 'extended', '80'], default='original',
                       help='Which repair results to use (default: original)')
    args = parser.parse_args()
    
    # Load repair results
    repair_map = load_repair_results(mode=args.mode)
    
    # Collect statistics by model-predicate
    stats = defaultdict(lambda: {
        'unique': 0,
        'correct': 0,
        'syntax_error': 0,
        'wrong': 0,
        'wrong_ids': [],  # Store unique_ids for wrong predicates
    })
    
    # Parse all result files
    for model_name, predicates in MODEL_PREDICATES.items():
        result_file = RESULTS_DIR / f"{model_name}.txt"
        
        if not result_file.exists():
            continue
        
        # Determine if this is a single-predicate model
        is_single_predicate_model = len(predicates) == 1
        
        # Parse with appropriate logic
        all_predicates = parse_result_file(result_file, is_single_predicate_model=is_single_predicate_model)
        
        # Check if predicates have names (for multi-predicate models, they should)
        # For single-predicate models, names will be None
        has_named_predicates = any(p['name'] is not None for p in all_predicates)
        
        if has_named_predicates:
            # Build wrong_ids using the same global index order as extract_wrong_predicates:
            # for pred_name in predicates: for pred_data in all_predicates: if Wrong -> index i (global per model)
            global_wrong_index = 0
            for pred_name in predicates:
                key = f"{model_name}-{pred_name}"
                wrong_ids = []
                for pred_data in all_predicates:
                    if pred_data['name'] == pred_name:
                        stats[key]['unique'] += 1
                        if pred_data['status'] == 'Correct':
                            stats[key]['correct'] += 1
                        elif pred_data['status'] == 'Syntax Error':
                            stats[key]['syntax_error'] += 1
                        elif pred_data['status'] == 'Wrong':
                            stats[key]['wrong'] += 1
                            wrong_ids.append(f"{model_name}_{pred_name}_{global_wrong_index}")
                            global_wrong_index += 1
                stats[key]['wrong_ids'] = wrong_ids
        else:
            # Single-predicate model
            if len(predicates) == 1:
                pred_name = predicates[0]
                key = f"{model_name}-{pred_name}"
                wrong_count = 0
                wrong_ids = []
                
                for i, pred_data in enumerate(all_predicates):
                    stats[key]['unique'] += 1
                    if pred_data['status'] == 'Correct':
                        stats[key]['correct'] += 1
                    elif pred_data['status'] == 'Syntax Error':
                        stats[key]['syntax_error'] += 1
                    elif pred_data['status'] == 'Wrong':
                        stats[key]['wrong'] += 1
                        wrong_count += 1
                        wrong_ids.append(f"{model_name}_{pred_name}_{wrong_count - 1}")
                
                stats[key]['wrong_ids'] = wrong_ids
    
    # Calculate repairable counts
    for key in stats:
        wrong_ids = stats[key]['wrong_ids']
        repairable_count = 0
        na_count = 0
        for wid in wrong_ids:
            status = repair_map.get(wid)
            if status is True:
                repairable_count += 1
            elif status is None:
                na_count += 1
        
        if args.mode == 'extended' and na_count > 0:
            # In extended mode, if any are NA, show as "N/A" or count with NA note
            stats[key]['repairable'] = repairable_count
            stats[key]['na_count'] = na_count
            stats[key]['has_na'] = True
        else:
            stats[key]['repairable'] = repairable_count
            stats[key]['na_count'] = 0
            stats[key]['has_na'] = False
    
    # Generate LaTeX table
    mode_suffix = f"_{args.mode}" if args.mode != 'original' else ""
    output_file = OUTPUT_DIR / f"ARepair_results_with_repairable{mode_suffix}.tex"
    
    mode_label = args.mode.upper() if args.mode != 'original' else 'Original'
    
    with open(output_file, 'w') as f:
        f.write("\\documentclass{article}\n\n")
        f.write("% --- Required Packages ---\n")
        f.write("\\usepackage{booktabs}\n")
        f.write("\\usepackage{caption}\n")
        f.write("\\usepackage{graphicx}\n")
        f.write("% ------------------\n\n")
        f.write("\\usepackage[margin=1in]{geometry}\n\n")
        f.write("\\begin{document}\n\n")
        f.write("\\begin{table}[ht]\n")
        f.write("\\centering\n")
        f.write(f"\\caption{{ARepair Dataset Results by Predicate (Gemini) with Repairable Column - {mode_label} Mode}}\n")
        f.write(f"\\label{{tab_arepair_by_predicate_with_repairable{mode_suffix}}}\n\n")
        f.write("\\resizebox{\\textwidth}{!}{%\n")
        # Use 'l' for Repairable column if extended mode (may contain text like "N/A" or "4 (2 NA)")
        col_spec = "lrrrrl" if args.mode == 'extended' else "lrrrrr"
        f.write(f"\\begin{{tabular}}{{{col_spec}}}\n")
        f.write("\\toprule\n")
        f.write("\\textbf{Model-Predicate} & \\textbf{Unique} & \\textbf{Correct} & \\textbf{Syntax Error} & \\textbf{Wrong} & \\textbf{Repairable} \\\\\n")
        f.write("\\midrule\n")
        
        # Sort keys for consistent output
        sorted_keys = sorted(stats.keys())
        
        for key in sorted_keys:
            s = stats[key]
            if args.mode == 'extended' and s['has_na'] and s['wrong'] > 0:
                # Show repairable count, with note that some are NA
                # Format: "4 (2 NA)" or just "4" if all are NA
                if s['na_count'] == s['wrong']:
                    repairable_str = "N/A"
                elif s['na_count'] > 0:
                    repairable_str = f"{s['repairable']} ({s['na_count']} NA)"
                else:
                    repairable_str = str(s['repairable'])
            else:
                repairable_str = str(s['repairable'])
            
            f.write(f"{key.replace('-', '-')} & {s['unique']} & {s['correct']} & {s['syntax_error']} & {s['wrong']} & {repairable_str} \\\\\n")
        
        # Totals
        total_unique = sum(s['unique'] for s in stats.values())
        total_correct = sum(s['correct'] for s in stats.values())
        total_syntax_error = sum(s['syntax_error'] for s in stats.values())
        total_wrong = sum(s['wrong'] for s in stats.values())
        total_repairable = sum(s['repairable'] for s in stats.values())
        total_na = sum(s.get('na_count', 0) for s in stats.values())
        
        f.write("\\midrule\n")
        if args.mode == 'extended' and total_na > 0:
            total_repairable_str = f"{total_repairable} ({total_na} NA)"
        else:
            total_repairable_str = str(total_repairable)
        f.write(f"\\textbf{{Totals}} & \\textbf{{{total_unique}}} & \\textbf{{{total_correct}}} & \\textbf{{{total_syntax_error}}} & \\textbf{{{total_wrong}}} & \\textbf{{{total_repairable_str}}} \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}%\n")
        f.write("} % --- End of \\resizebox ---\n")
        f.write("\\end{table}\n\n")
        f.write("\\end{document}\n")
    
    print(f"Summary table with Repairable column saved to: {output_file}")
    print(f"\nSummary ({args.mode} mode):")
    print(f"  Total predicate types: {len(sorted_keys)}")  # Number of different predicate types (model-predicate combinations)
    print(f"  Total Unique samples: {total_unique}")  # Total number of samples (usually 20 types × 10 samples = 200)
    print(f"  Total Wrong: {total_wrong}")
    print(f"  Total Repairable: {total_repairable}")
    if args.mode == 'extended' and total_na > 0:
        print(f"  Total NA (skipped): {total_na}")
        applicable_wrong = total_wrong - total_na
        if applicable_wrong > 0:
            print(f"  Repairable rate (applicable): {total_repairable / applicable_wrong * 100:.1f}%")
        else:
            print(f"  Repairable rate (applicable): N/A (all skipped)")
    else:
        print(f"  Repairable rate: {total_repairable / total_wrong * 100:.1f}%" if total_wrong > 0 else "  Repairable rate: N/A")

if __name__ == "__main__":
    main()
