#!/usr/bin/env python
"""
Compare WithTest vs NoTest Alloy evaluation results by model-predicate.

Reads result/Gemini/ARepair/Alloy/*.txt and result/Gemini/ARepairNoTest/Alloy/*.txt,
parses per-predicate Correct/Syntax Error/Wrong, outputs a readable model-pred table.
Optionally includes Repairable counts if repair_results.json paths are given.
Optionally writes LaTeX (unless --no-tex).

Usage:
  python compare_with_vs_without_test.py
  python compare_with_vs_without_test.py --no-tex
  python compare_with_vs_without_test.py --tex-suffix gemini-3-flash-preview
  python compare_with_vs_without_test.py --output-tex /path/to/out.tex
  python compare_with_vs_without_test.py --repair-with result/Gemini/ARepair/RepairResults/repair_results.json --repair-no result/Gemini/ARepairNoTest/RepairResults/repair_results.json
"""

import argparse
import json
from pathlib import Path
from typing import Dict, Optional, Tuple

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()
AREPAIR_ALLOY = BASE_DIR / "result/Gemini/ARepair/Alloy"
NOTEST_ALLOY = BASE_DIR / "result/Gemini/ARepairNoTest/Alloy"
REPAIR_RESULTS_WITH = BASE_DIR / "result/Gemini/ARepair/RepairResults/repair_results.json"
REPAIR_RESULTS_NO = BASE_DIR / "result/Gemini/ARepairNoTest/RepairResults/repair_results.json"
OUTPUT_TEX_DEFAULT = (
    BASE_DIR
    / "result"
    / "thesis"
    / "RQ1_TestVsNoTest"
    / "tables"
    / "with_vs_no_test_by_predicate.tex"
)


def _sanitize_tex_suffix(s: str) -> str:
    """Safe filename fragment (Gemini model id, etc.)."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s.strip())


def _latex_label_suffix(safe_suffix: str) -> str:
    """LaTeX \\label token (avoid duplicate labels across runs)."""
    return "".join(c if c.isalnum() else "" for c in safe_suffix) or "default"


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


def parse_result_file_to_pred_counts(path: Path, model_name: str) -> Dict[str, dict]:
    """
    Parse an Alloy result file and return per-predicate counts: pred_name -> {Correct, Syntax Error, Wrong}.
    """
    out = {}  # pred_name -> {Correct, Syntax Error, Wrong}
    preds = MODEL_PREDICATES.get(model_name, [])
    is_single = len(preds) == 1
    single_pred_name = preds[0] if is_single else None

    if not path.is_file():
        return out
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("Total:") or line.startswith("Unique:"):
            i += 1
            continue
        status = None
        pred_name = None
        if is_single:
            if i + 1 < len(lines) and lines[i + 1].strip() in ("Correct", "Syntax Error", "Wrong"):
                status = lines[i + 1].strip()
                pred_name = single_pred_name
                i += 1
        else:
            if ":" in line:
                parts = line.split(":", 1)
                if len(parts) == 2 and i + 1 < len(lines):
                    pred_name = parts[0].strip()
                    next_line = lines[i + 1].strip()
                    if next_line in ("Correct", "Syntax Error", "Wrong"):
                        status = next_line
                        i += 1
            elif i + 1 < len(lines) and lines[i + 1].strip() in ("Correct", "Syntax Error", "Wrong"):
                status = lines[i + 1].strip()
                pred_name = None  # will not count if we can't assign
                i += 1
        i += 1
        if pred_name and status:
            if pred_name not in out:
                out[pred_name] = {"Correct": 0, "Syntax Error": 0, "Wrong": 0}
            out[pred_name][status] = out[pred_name].get(status, 0) + 1

    # Fallback for single-predicate model when file has only summary (no body+status lines).
    # Java may write only "Total:/Correct:/Syntax Error:/Wrong:" when it skips arr ("No predicates to repair").
    if is_single and single_pred_name and single_pred_name not in out:
        summary_c = summary_se = summary_w = None
        for line in lines:
            s = line.strip()
            if s.startswith("Correct:"):
                try:
                    summary_c = int(s.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif s.startswith("Syntax Error:"):
                try:
                    summary_se = int(s.split(":", 1)[1].strip())
                except ValueError:
                    pass
            elif s.startswith("Wrong:"):
                try:
                    summary_w = int(s.split(":", 1)[1].strip())
                except ValueError:
                    pass
        if summary_c is not None and summary_se is not None and summary_w is not None:
            out[single_pred_name] = {
                "Correct": summary_c,
                "Syntax Error": summary_se,
                "Wrong": summary_w,
            }
    return out


def load_repair_counts(path: Path) -> Dict[str, int]:
    """
    Load repair_results.json and return per model-predicate repairable count.
    unique_id format: model_name_pred_name_index. Repairable = SUCCESS or PARTIAL.
    """
    out = {}  # model_pred -> count of repairable
    if not path.is_file():
        return out
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    for item in data:
        uid = item.get("unique_id", "")
        status = item.get("status", "")
        if status in ("SUCCESS", "PARTIAL"):
            # model_name_pred_name_index -> model_name-pred_name
            parts = uid.rsplit("_", 1)
            if len(parts) == 2:
                model_pred = parts[0].replace("_", "-", 1)
                out[model_pred] = out.get(model_pred, 0) + 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare WithTest vs NoTest by model-predicate")
    parser.add_argument("--no-tex", action="store_true", help="Do not write LaTeX file")
    parser.add_argument(
        "--output-tex",
        type=str,
        default=None,
        help="Full path for LaTeX output (overrides --tex-suffix and default).",
    )
    parser.add_argument(
        "--tex-suffix",
        type=str,
        default=None,
        help="Write result/with_vs_no_test_by_predicate_<suffix>.tex (avoids overwriting).",
    )
    parser.add_argument("--with-alloy-dir", type=str, default=None,
                        help="WithTest Alloy dir (e.g. result/thesis/.../WithTest/Alloy)")
    parser.add_argument("--no-alloy-dir", type=str, default=None,
                        help="NoTest Alloy dir (e.g. result/thesis/.../NoTest/Alloy)")
    parser.add_argument("--repair-with", type=str, default=None,
                        help="Path to WithTest repair_results.json (add Rep column)")
    parser.add_argument("--repair-no", type=str, default=None,
                        help="Path to NoTest repair_results.json (add Rep column)")
    parser.add_argument(
        "--cor-syn-sem-only",
        action="store_true",
        help="Ignore repair_results.json; print/write only Cor (Correct), Syn (Syntax Error), Sem (Wrong).",
    )
    parser.add_argument(
        "--bench-models",
        type=str,
        default="",
        help="Comma-separated benchmark names (e.g. arr). If set, only those models appear (matches partial Java eval).",
    )
    args = parser.parse_args()

    if args.output_tex:
        output_tex_path = Path(args.output_tex).expanduser().resolve()
    elif args.tex_suffix:
        suf = _sanitize_tex_suffix(args.tex_suffix)
        output_tex_path = (
            BASE_DIR
            / "result"
            / "thesis"
            / "RQ1_TestVsNoTest"
            / "tables"
            / f"with_vs_no_test_by_predicate_{suf}.tex"
        )
    else:
        output_tex_path = OUTPUT_TEX_DEFAULT

    with_alloy = Path(args.with_alloy_dir) if args.with_alloy_dir else AREPAIR_ALLOY
    no_alloy = Path(args.no_alloy_dir) if args.no_alloy_dir else NOTEST_ALLOY
    repair_with_path = Path(args.repair_with) if args.repair_with else (with_alloy.parent / "RepairResults" / "repair_results.json")
    repair_no_path = Path(args.repair_no) if args.repair_no else (no_alloy.parent / "RepairResults" / "repair_results.json")
    with_repair = (
        (not args.cor_syn_sem_only)
        and repair_with_path.is_file()
        and repair_no_path.is_file()
    )

    bench_allow = None
    if args.bench_models and args.bench_models.strip():
        bench_allow = {p.strip() for p in args.bench_models.split(",") if p.strip()}
        print("Bench filter (table rows):", sorted(bench_allow))

    # Build rows: (model_pred, with_counts, no_counts) for each model-pred
    rows = []
    for model_name in sorted(MODEL_PREDICATES.keys()):
        if bench_allow is not None and model_name not in bench_allow:
            continue
        preds = MODEL_PREDICATES[model_name]
        with_path = with_alloy / f"{model_name}.txt"
        no_path = no_alloy / f"{model_name}.txt"
        with_counts = parse_result_file_to_pred_counts(with_path, model_name)
        no_counts = parse_result_file_to_pred_counts(no_path, model_name)
        for pred_name in preds:
            model_pred = f"{model_name}-{pred_name}"
            w = with_counts.get(pred_name, {"Correct": 0, "Syntax Error": 0, "Wrong": 0})
            n = no_counts.get(pred_name, {"Correct": 0, "Syntax Error": 0, "Wrong": 0})
            rows.append((model_pred, w, n))

    if not rows:
        print("No model-predicate rows (missing Alloy result files?).")
        return

    rep_with = load_repair_counts(repair_with_path) if with_repair else {}
    rep_no = load_repair_counts(repair_no_path) if with_repair else {}

    # Data source hint (if WithTest == NoTest everywhere, likely same files)
    print("Data: WithTest =", with_alloy, "| NoTest =", no_alloy)
    all_same = all(
        w.get("Correct", 0) == n.get("Correct", 0)
        and w.get("Syntax Error", 0) == n.get("Syntax Error", 0)
        and w.get("Wrong", 0) == n.get("Wrong", 0)
        for _, w, n in rows
    )
    has_data = any(
        w.get("Correct", 0) + w.get("Syntax Error", 0) + w.get("Wrong", 0) != 0
        for _, w, _ in rows
    )
    if all_same and has_data:
        print("WARNING: WithTest and NoTest counts are identical for every row.")
        print("  -> Did you run evaluate_notest_responses.py with NoTest responses in result/Gemini/ARepairNoTest/responses/?")
        print("  -> If ARepairNoTest/Alloy was copied from ARepair/Alloy, replace it with real NoTest evaluation output.")
    print()

    # --- Readable table (primary output), model-pred per row ---
    col_w = 22
    sep = " | "
    if with_repair:
        header = (
            "Model-Predicate".ljust(col_w) + sep +
            "WithTest (Cor / Syn / Sem)".ljust(20) + sep +
            "NoTest (Cor / Syn / Sem)".ljust(20) + sep +
            "WithRep".ljust(8) + sep +
            "NoRep".ljust(8) + sep +
            "Delta (Cor / Syn / Sem)"
        )
    else:
        header = (
            "Model-Predicate".ljust(col_w) + sep +
            "WithTest (Cor / Syn / Sem)".ljust(20) + sep +
            "NoTest (Cor / Syn / Sem)".ljust(20) + sep +
            "Delta (Cor / Syn / Sem)"
        )
    print(header)
    print("-" * len(header))
    tot_w = {"Correct": 0, "Syntax Error": 0, "Wrong": 0}
    tot_n = {"Correct": 0, "Syntax Error": 0, "Wrong": 0}
    tot_rep_w = tot_rep_n = 0

    def fmt_counts(c):
        return f"{c.get('Correct', 0)} / {c.get('Syntax Error', 0)} / {c.get('Wrong', 0)}"

    for model_pred, w, n in rows:
        with_str = fmt_counts(w)
        no_str = fmt_counts(n)
        dc = n.get("Correct", 0) - w.get("Correct", 0)
        dse = n.get("Syntax Error", 0) - w.get("Syntax Error", 0)
        dw = n.get("Wrong", 0) - w.get("Wrong", 0)
        delta = f"{dc:+d} / {dse:+d} / {dw:+d}"
        for k in tot_w:
            tot_w[k] += w.get(k, 0)
            tot_n[k] += n.get(k, 0)
        if with_repair:
            rw = rep_with.get(model_pred, 0)
            rn = rep_no.get(model_pred, 0)
            tot_rep_w += rw
            tot_rep_n += rn
            print(model_pred.ljust(col_w) + sep + with_str.ljust(20) + sep + no_str.ljust(20) + sep + str(rw).ljust(8) + sep + str(rn).ljust(8) + sep + delta)
        else:
            print(model_pred.ljust(col_w) + sep + with_str.ljust(20) + sep + no_str.ljust(20) + sep + delta)
    print("-" * len(header))
    total_line = "Total".ljust(col_w) + sep + fmt_counts(tot_w).ljust(20) + sep + fmt_counts(tot_n).ljust(20)
    if with_repair:
        total_line += sep + str(tot_rep_w).ljust(8) + sep + str(tot_rep_n).ljust(8)
    print(total_line)
    print()
    print("Cor = Correct, Syn = Syntax Error, Sem = Semantic error (Wrong). Delta = NoTest - WithTest." + (" WithRep/NoRep = repairable count (SUCCESS+PARTIAL)." if with_repair else ""))

    # LaTeX (optional)
    if not args.no_tex:
        if args.output_tex:
            label_line = "\\label{tab_with_vs_no_test_custom}"
        elif args.tex_suffix:
            tok = _latex_label_suffix(_sanitize_tex_suffix(args.tex_suffix))
            label_line = f"\\label{{tab_with_vs_no_test_{tok}}}"
        else:
            label_line = "\\label{tab_with_vs_no_test}"

        output_tex_path.parent.mkdir(parents=True, exist_ok=True)
        tex_lines = [
            "\\begin{table}[ht]",
            "\\centering",
            "\\caption{WithTest vs NoTest (prompt with/without test suite) by Model-Predicate}",
            label_line,
            "",
            "\\resizebox{\\textwidth}{!}{%",
            "\\begin{tabular}{lrrrrrr}",
            "\\toprule",
            "\\textbf{Model-Predicate} & \\multicolumn{3}{c}{\\textbf{WithTest}} & \\multicolumn{3}{c}{\\textbf{NoTest}} \\\\",
            " & Cor & Syn & Sem & Cor & Syn & Sem \\\\",
            "\\midrule",
        ]
        for model_pred, w, n in rows:
            cw, sew, ww = w.get("Correct", 0), w.get("Syntax Error", 0), w.get("Wrong", 0)
            cn, sen, wn = n.get("Correct", 0), n.get("Syntax Error", 0), n.get("Wrong", 0)
            tex_lines.append(f"{model_pred} & {cw} & {sew} & {ww} & {cn} & {sen} & {wn} \\\\")
        tex_lines.extend([
            "\\midrule",
            f"\\textbf{{Total}} & \\textbf{{{tot_w['Correct']}}} & \\textbf{{{tot_w['Syntax Error']}}} & \\textbf{{{tot_w['Wrong']}}} & \\textbf{{{tot_n['Correct']}}} & \\textbf{{{tot_n['Syntax Error']}}} & \\textbf{{{tot_n['Wrong']}}} \\\\",
            "\\bottomrule",
            "\\end{tabular}%",
            "}",
            "\\end{table}",
        ])
        output_tex_path.write_text("\n".join(tex_lines), encoding="utf-8")
        print("LaTeX table written to:", output_tex_path)
    elif with_repair:
        print("(Use without --no-tex to also write LaTeX.)")


if __name__ == "__main__":
    main()
