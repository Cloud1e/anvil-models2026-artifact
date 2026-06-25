#!/usr/bin/env python
"""
Generate combined summary table with Repairable columns for Original, Extended, and 80% modes.
Extended and 80% columns will be colored (red and blue respectively).
"""

import json
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
    """Parse a result file and extract predicates with their status."""
    predicates = []
    
    with open(result_file, 'r') as f:
        lines = f.readlines()
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line.startswith('Total:') or line.startswith('Unique:'):
            i += 1
            continue
        
        if not line:
            i += 1
            continue
        
        if is_single_predicate_model:
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

def load_repair_results(mode='original'):
    """Load ARepair results.
    
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
    
    repair_map = {}
    for result in results:
        unique_id = result['unique_id']
        status = result['status']
        if status == 'NA':
            repair_map[unique_id] = None
        elif status in ['SUCCESS', 'PARTIAL']:
            repair_map[unique_id] = True
        else:
            repair_map[unique_id] = False
    
    return repair_map

def main():
    """Generate combined summary table with three Repairable columns."""
    
    # Load repair results for all three modes
    repair_map_original = load_repair_results(mode='original')
    repair_map_extended = load_repair_results(mode='extended')
    repair_map_80 = load_repair_results(mode='80')
    
    # Collect statistics by model-predicate
    stats = defaultdict(lambda: {
        'unique': 0,
        'correct': 0,
        'syntax_error': 0,
        'wrong': 0,
        'wrong_ids': [],
    })
    
    # Parse all result files
    for model_name, predicates in MODEL_PREDICATES.items():
        result_file = RESULTS_DIR / f"{model_name}.txt"
        
        if not result_file.exists():
            continue
        
        is_single_predicate_model = len(predicates) == 1
        all_predicates = parse_result_file(result_file, is_single_predicate_model=is_single_predicate_model)
        has_named_predicates = any(p['name'] is not None for p in all_predicates)
        
        if has_named_predicates:
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
    
    # Calculate repairable counts for each mode
    for key in stats:
        wrong_ids = stats[key]['wrong_ids']
        
        # Original mode
        repairable_original = 0
        for wid in wrong_ids:
            if repair_map_original.get(wid) is True:
                repairable_original += 1
        stats[key]['repairable_original'] = repairable_original
        
        # Extended mode
        repairable_extended = 0
        na_extended = 0
        for wid in wrong_ids:
            status = repair_map_extended.get(wid)
            if status is True:
                repairable_extended += 1
            elif status is None:
                na_extended += 1
        stats[key]['repairable_extended'] = repairable_extended
        stats[key]['na_extended'] = na_extended
        
        # 80% mode
        repairable_80 = 0
        for wid in wrong_ids:
            if repair_map_80.get(wid) is True:
                repairable_80 += 1
        stats[key]['repairable_80'] = repairable_80
    
    # Generate LaTeX table
    output_file = BASE_DIR / "arepair_combined_by_predicate.tex"
    
    with open(output_file, 'w') as f:
        f.write("\\resizebox{\\textwidth}{!}{%\n")
        f.write("\\begin{tabular}{lrrrrrrr}\n")
        f.write("\\toprule\n")
        f.write("\\textbf{Model-Predicate} & \\textbf{Unique} & \\textbf{Correct} & \\textbf{Syntax Error} & \\textbf{Wrong} & \\textbf{Repairable (Original)} & \\textcolor{red}{\\textbf{Repairable (Extended)}} & \\textcolor{blue}{\\textbf{Repairable (80\\%)}} \\\\\n")
        f.write("\\midrule\n")
        
        sorted_keys = sorted(stats.keys())
        
        for key in sorted_keys:
            s = stats[key]
            
            # Extended mode should only be used when both Wrong > 0 and Correct > 0
            # If Correct=0 or Wrong=0, Extended should be N/A
            should_be_na = (s['correct'] == 0) or (s['wrong'] == 0)
            
            # Format extended repairable (handle NA and show comparison with original)
            if should_be_na:
                repairable_extended_str = "\\textcolor{red}{N/A}"
            elif s['na_extended'] > 0:
                if s['na_extended'] == s['wrong']:
                    repairable_extended_str = "\\textcolor{red}{N/A}"
                else:
                    # Compare with original
                    diff = s['repairable_extended'] - s['repairable_original']
                    if diff > 0:
                        diff_str = f"+{diff}"
                    elif diff < 0:
                        diff_str = str(diff)
                    else:
                        diff_str = "="
                    repairable_extended_str = f"\\textcolor{{red}}{{{s['repairable_extended']} ({diff_str}, {s['na_extended']} NA)}}"
            else:
                # Compare with original
                diff = s['repairable_extended'] - s['repairable_original']
                if diff > 0:
                    diff_str = f"+{diff}"
                elif diff < 0:
                    diff_str = str(diff)
                else:
                    diff_str = "="
                # Always show comparison, including when equal
                repairable_extended_str = f"\\textcolor{{red}}{{{s['repairable_extended']} ({diff_str})}}"
            
            # Format 80% repairable (show comparison with original)
            diff_80 = s['repairable_80'] - s['repairable_original']
            if diff_80 > 0:
                diff_80_str = f"+{diff_80}"
            elif diff_80 < 0:
                diff_80_str = str(diff_80)
            else:
                diff_80_str = "="
            # Always show comparison, including when equal
            repairable_80_str = f"\\textcolor{{blue}}{{{s['repairable_80']} ({diff_80_str})}}"
            
            f.write(f"{key.replace('-', '-')} & {s['unique']} & {s['correct']} & {s['syntax_error']} & {s['wrong']} & {s['repairable_original']} & {repairable_extended_str} & {repairable_80_str} \\\\\n")
        
        # Totals
        total_unique = sum(s['unique'] for s in stats.values())
        total_correct = sum(s['correct'] for s in stats.values())
        total_syntax_error = sum(s['syntax_error'] for s in stats.values())
        total_wrong = sum(s['wrong'] for s in stats.values())
        total_repairable_original = sum(s['repairable_original'] for s in stats.values())
        total_repairable_extended = sum(s['repairable_extended'] for s in stats.values())
        total_repairable_80 = sum(s['repairable_80'] for s in stats.values())
        total_na_extended = sum(s['na_extended'] for s in stats.values())
        
        # Format totals (show comparison with original)
        # Count how many Wrong predicates should be N/A (Correct=0 or Wrong=0)
        # This is the number of Wrong cases that were skipped because the predicate doesn't have both Wrong and Correct
        total_na_by_condition = 0
        for key in sorted_keys:
            s = stats[key]
            if (s['correct'] == 0) or (s['wrong'] == 0):
                # All Wrong cases for this predicate should be skipped
                total_na_by_condition += s['wrong']
        
        # Total NA = condition-based NA (no both wrong+correct) + actual skipped ones (no extended tests found)
        # But we should only count the condition-based ones, since those are the ones we're tracking
        # The actual skipped ones (s['na_extended']) are already included in the condition check
        # Actually, s['na_extended'] is from the repair results JSON, which only counts actual skips
        # So total_na_by_condition counts skips due to condition, and total_na_extended counts other skips
        # But wait - if condition is not met, the repair won't run, so s['na_extended'] should be 0 for those
        # Let me recalculate: total NA = sum of wrong counts where condition not met
        total_na_all = total_na_by_condition
        
        total_diff_extended = total_repairable_extended - total_repairable_original
        if total_na_all > 0:
            applicable_wrong = total_wrong - total_na_all
            if applicable_wrong == 0:
                total_extended_str = "\\textcolor{red}{N/A}"
            else:
                if total_diff_extended > 0:
                    diff_str = f"+{total_diff_extended}"
                elif total_diff_extended < 0:
                    diff_str = str(total_diff_extended)
                else:
                    diff_str = "="
                total_extended_str = f"\\textcolor{{red}}{{{total_repairable_extended} ({diff_str}, {total_na_all} NA)}}"
        else:
            if total_diff_extended > 0:
                diff_str = f"+{total_diff_extended}"
            elif total_diff_extended < 0:
                diff_str = str(total_diff_extended)
            else:
                diff_str = "="
            # Always show comparison, including when equal
            total_extended_str = f"\\textcolor{{red}}{{{total_repairable_extended} ({diff_str})}}"
        
        total_diff_80 = total_repairable_80 - total_repairable_original
        if total_diff_80 > 0:
            diff_80_str = f"+{total_diff_80}"
        elif total_diff_80 < 0:
            diff_80_str = str(total_diff_80)
        else:
            diff_80_str = "="
        # Always show comparison, including when equal
        total_80_str = f"\\textcolor{{blue}}{{{total_repairable_80} ({diff_80_str})}}"
        
        f.write("\\midrule\n")
        f.write(f"\\textbf{{Totals}} & \\textbf{{{total_unique}}} & \\textbf{{{total_correct}}} & \\textbf{{{total_syntax_error}}} & \\textbf{{{total_wrong}}} & \\textbf{{{total_repairable_original}}} & \\textbf{{{total_extended_str}}} & \\textbf{{{total_80_str}}} \\\\\n")
        f.write("\\bottomrule\n")
        f.write("\\end{tabular}%\n")
        f.write("} % --- End of \\resizebox ---\n")
    
    print(f"Combined summary table saved to: {output_file}")
    print(f"\nSummary:")
    print(f"  Total predicate types: {len(sorted_keys)}")
    print(f"  Total Unique samples: {total_unique}")
    print(f"  Total Wrong: {total_wrong}")
    print(f"  Total Repairable (Original): {total_repairable_original}")
    print(f"  Total Repairable (Extended): {total_repairable_extended}")
    if total_na_extended > 0:
        print(f"    - NA (skipped): {total_na_extended}")
    print(f"  Total Repairable (80%): {total_repairable_80}")
    
    # Print rates
    if total_wrong > 0:
        print(f"\nRepairable rates:")
        print(f"  Original: {total_repairable_original / total_wrong * 100:.1f}%")
        applicable_wrong = total_wrong - total_na_extended
        if applicable_wrong > 0:
            print(f"  Extended: {total_repairable_extended / applicable_wrong * 100:.1f}% (of applicable)")
        else:
            print(f"  Extended: N/A (all skipped)")
        print(f"  80%: {total_repairable_80 / total_wrong * 100:.1f}%")

if __name__ == "__main__":
    main()
