#!/usr/bin/env python
"""
Aggregate RQ3 faulty-rewrite artifacts into numbers for Table E (LaTeX).

Reads per-model output under:
  result/Gemini/RQ3_Repair/FaultyRewrite/<gemini-model>/
    classification.json
    RepairResultsOriginal/repair_results.json
    RepairResultsLLM/repair_results.json

For each predicate (non-NA rows in the paper table):
  - LLM (10x): Cor / Syn / Sem counts from classification.json (kind == llm)
  - Orig: repaired / total Sem for the *original* faulty model (same inputs for all LLMs;
    denominator is 1 if the original is Sem, else NA — table uses 0/1 style)
  - LLM (ARepair): among LLM rewrites classified as Sem, count SUCCESS+PARTIAL / total Sem

NA predicates (arr, bempl, cd-ClassHierarchy, farmer-solvePuzzle) are skipped.

Usage (from repo root):
  python scripts/faulty/summarize_table_e.py \\
    --info-root result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3.1-pro-preview
  python scripts/faulty/summarize_table_e.py --flash --lite

Write per-model LaTeX fragments without overwriting (use --write-tex and optional --tex-suffix):
  python scripts/faulty/summarize_table_e.py --flash --write-tex
  # -> result/table_e_rq3_faulty_gemini-3-flash-preview.tex
  python scripts/faulty/summarize_table_e.py --info-root ... --write-tex --tex-suffix run20260322
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()

DEFAULT_TEX_DIR = BASE_DIR / "result" / "thesis" / "RQ2_FaultyRewrite_ARepair" / "tables"
DEFAULT_TEX_STEM = "table_e_rq3_faulty"

# Paper row order; value is None for NA rows (multicolumn NA in TeX).
TABLE_ROWS: List[Tuple[str, str | None]] = [
    ("arr", "NoConflict"),  # NA
    ("balancedBST", "Balanced"),
    ("balancedBST", "HasAtMostOneChild"),
    ("balancedBST", "Sorted"),
    ("bempl", "CanEnter"),  # NA
    ("cd", "Acyclic"),
    ("cd", "AllExtObject"),
    ("cd", "ClassHierarchy"),  # NA
    ("cd", "ObjectNoExt"),
    ("dll", "ConsistentPreAndNxt"),
    ("dll", "Sorted"),
    ("dll", "UniqueElem"),
    ("farmer", "crossRiver"),
    ("farmer", "solvePuzzle"),  # NA
    ("grade", "PolicyAllowsGrading"),
    ("other", "CanEnter"),
    ("student", "Contains"),
    ("student", "Count"),
    ("student", "Loop"),
    ("student", "Sorted"),
]

NA_KEYS = {
    ("arr", "NoConflict"),
    ("bempl", "CanEnter"),
    ("cd", "ClassHierarchy"),
    ("farmer", "solvePuzzle"),
}


def _sanitize_tex_suffix(s: str) -> str:
    """Safe filename fragment (Gemini model id, run tag, etc.)."""
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in s.strip())


def _load_json(path: Path):
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _repair_ok(status: str) -> bool:
    return status in ("SUCCESS", "PARTIAL")


def _suffix_for_info_root(info_root: Path) -> str:
    """e.g. .../gemini-3-flash-preview -> gemini-3-flash-preview."""
    info_root = info_root.resolve()
    return _sanitize_tex_suffix(info_root.name)


def aggregate_one_model(
    info_root: Path,
    *,
    quiet: bool = False,
) -> Tuple[bool, str, str, str]:
    """
    Returns (ok, report_text, latex_fragment, default_suffix).
    If not ok, latex_fragment is empty.
    """
    info_root = info_root.resolve()
    cls_path = info_root / "classification.json"
    orig_rep = info_root / "RepairResultsOriginal" / "repair_results.json"
    llm_rep = info_root / "RepairResultsLLM" / "repair_results.json"
    default_suffix = _suffix_for_info_root(info_root)

    cls = _load_json(cls_path)
    if not cls:
        msg = f"[skip] missing classification.json: {cls_path}\n"
        if not quiet:
            sys.stdout.write(msg)
        return False, msg, "", default_suffix

    orig_results = _load_json(orig_rep)
    llm_results = _load_json(llm_rep)
    if not orig_results or not llm_results:
        msg = f"[skip] missing repair_results under {info_root}\n"
        if not quiet:
            sys.stdout.write(msg)
        return False, msg, "", default_suffix

    orig_status = {r["unique_id"]: r.get("status", "") for r in orig_results}
    llm_status = {r["unique_id"]: r.get("status", "") for r in llm_results}

    by_pred_llm: Dict[Tuple[str, str], List[dict]] = defaultdict(list)
    by_pred_orig: Dict[Tuple[str, str], List[dict]] = defaultdict(list)

    for r in cls.get("results", []):
        kind = r.get("kind")
        mn = r.get("model_name", "")
        pn = r.get("predicate_name", "")
        key = (mn, pn)
        if kind == "llm":
            by_pred_llm[key].append(r)
        elif kind == "original":
            by_pred_orig[key].append(r)

    def fmt_pred(mn: str, pn: str) -> str:
        return f"{mn}-{pn}"

    lines_out: List[str] = []
    lines_out.append(f"=== Table E aggregates: {info_root} ===\n")

    tot_cor = tot_syn = tot_sem = 0
    tot_orig_num = tot_orig_den = 0
    tot_llm_rep_num = tot_llm_rep_den = 0

    for mn, pn in TABLE_ROWS:
        key = (mn, pn)
        label = fmt_pred(mn, pn)
        if key in NA_KEYS:
            lines_out.append(f"{label:32}  NA\n")
            continue

        orig_rows = by_pred_orig.get(key, [])
        llm_rows = by_pred_llm.get(key, [])

        cor = syn = sem = 0
        for r in llm_rows:
            res = r.get("result", "Unknown")
            if res == "Cor":
                cor += 1
            elif res == "Syn":
                syn += 1
            elif res == "Sem":
                sem += 1

        orig_s = ""
        if orig_rows:
            o = orig_rows[0]
            if o.get("result") == "Sem":
                uid = o.get("unique_id", "")
                ok = _repair_ok(orig_status.get(uid, ""))
                n = 1 if ok else 0
                orig_s = f"{n}/1"
                tot_orig_num += n
                tot_orig_den += 1
            else:
                orig_s = "0/0?"
        else:
            orig_s = "missing"

        sem_uids = [r["unique_id"] for r in llm_rows if r.get("result") == "Sem"]
        rep_n = sum(1 for u in sem_uids if _repair_ok(llm_status.get(u, "")))
        rep_d = len(sem_uids)
        llm_s = f"{rep_n}/{rep_d}" if rep_d else "0/0"

        tot_cor += cor
        tot_syn += syn
        tot_sem += sem
        tot_llm_rep_num += rep_n
        tot_llm_rep_den += rep_d

        lines_out.append(
            f"{label:32}  "
            f"LLM {cor:2} {syn:2} {sem:2}   "
            f"Orig {orig_s:5}  LLMrep {llm_s}\n"
        )

    lines_out.append(
        f"\n{'TOTAL (data rows only)':32}  "
        f"LLM {tot_cor:2} {tot_syn:2} {tot_sem:2}   "
        f"Orig {tot_orig_num}/{tot_orig_den}  LLMrep {tot_llm_rep_num}/{tot_llm_rep_den}\n"
    )

    lines_out.append(
        "\nLaTeX fragment (5 cols: Cor Syn Sem Orig LLMrep), for Flash/Lite columns:\n\n"
    )

    tex_lines: List[str] = [
        f"% Auto-generated by scripts/faulty/summarize_table_e.py",
        f"% Source info_root: {info_root}",
        f"% Table E fragment: LLM Cor/Syn/Sem + Orig ARepair + LLM ARepair",
        f"% (No \\label here — add in the paper or use \\input inside a single table.)",
        "",
    ]

    for mn, pn in TABLE_ROWS:
        key = (mn, pn)
        label = fmt_pred(mn, pn)
        if key in NA_KEYS:
            lines_out.append(
                f"% {label} -> \\multicolumn{{3}}{{c|}}{{NA}} & NA & NA\n"
            )
            tex_lines.append(
                f"% {label}: \\multicolumn{{3}}{{c|}}{{NA}} & NA & NA  % NA row"
            )
            continue
        llm_rows = by_pred_llm.get(key, [])
        orig_rows = by_pred_orig.get(key, [])
        cor = syn = sem = 0
        for r in llm_rows:
            res = r.get("result", "Unknown")
            if res == "Cor":
                cor += 1
            elif res == "Syn":
                syn += 1
            elif res == "Sem":
                sem += 1
        orig_s = ""
        if orig_rows:
            o = orig_rows[0]
            if o.get("result") == "Sem":
                uid = o.get("unique_id", "")
                n = 1 if _repair_ok(orig_status.get(uid, "")) else 0
                orig_s = f"{n}/1"
        sem_uids = [r["unique_id"] for r in llm_rows if r.get("result") == "Sem"]
        rep_n = sum(1 for u in sem_uids if _repair_ok(llm_status.get(u, "")))
        rep_d = len(sem_uids)
        llm_s = f"{rep_n}/{rep_d}" if rep_d else "0/0"
        pad = " " * (31 - len(label))
        row_tex = f"{label}{pad} & {cor} & {syn} & {sem}  & {orig_s} & {llm_s}  \\\\"
        lines_out.append(row_tex + "\n")
        tex_lines.append(row_tex)

    tot_orig_line = f"\\textbf{{{tot_orig_num}/{tot_orig_den}}}"
    tot_llm_line = f"\\textbf{{{tot_llm_rep_num}/{tot_llm_rep_den}}}"
    tot_row = (
        f"\\textbf{{{tot_cor}}} & \\textbf{{{tot_syn}}} & \\textbf{{{tot_sem}}} & "
        f"{tot_orig_line} & {tot_llm_line} \\\\"
    )
    lines_out.append(tot_row + "\n")
    tex_lines.append(tot_row)

    report_text = "".join(lines_out)
    latex_text = "\n".join(tex_lines) + "\n"

    if not quiet:
        sys.stdout.write(report_text + "\n")

    return True, report_text, latex_text, default_suffix


def main() -> None:
    ap = argparse.ArgumentParser(description="Summarize RQ3 faulty artifacts for Table E.")
    ap.add_argument(
        "--info-root",
        default="",
        help="Path to per-model output root for one Gemini model (relative to repo root).",
    )
    ap.add_argument(
        "--flash",
        action="store_true",
        help="Shorthand for gemini-3-flash-preview RQ3 folder.",
    )
    ap.add_argument(
        "--lite",
        action="store_true",
        help="Shorthand for gemini-3.1-flash-lite-preview RQ3 folder.",
    )
    ap.add_argument(
        "--write-tex",
        action="store_true",
        help=(
            f"Write each model's LaTeX fragment to a separate file under {DEFAULT_TEX_DIR}/ "
            f"(default name {DEFAULT_TEX_STEM}_<suffix>.tex; suffix from --tex-suffix or model folder)."
        ),
    )
    ap.add_argument(
        "--tex-suffix",
        default="",
        help=(
            "Optional extra fragment for the .tex filename (e.g. run id). "
            "Final name: {stem}_{model_or_suffix}[_{tex-suffix}].tex when --write-tex is set."
        ),
    )
    ap.add_argument(
        "--output-tex",
        default="",
        help=(
            "Write LaTeX fragment to this exact path (single --info-root only). "
            "Overrides --write-tex naming."
        ),
    )
    ap.add_argument(
        "--tex-dir",
        default="",
        help=f"Directory for --write-tex files (default: {DEFAULT_TEX_DIR}).",
    )
    ap.add_argument(
        "--tex-stem",
        default=DEFAULT_TEX_STEM,
        help=f"Filename stem for --write-tex (default: {DEFAULT_TEX_STEM}).",
    )
    ap.add_argument(
        "--no-stdout",
        action="store_true",
        help="With --write-tex, do not print the human-readable report to stdout.",
    )
    args = ap.parse_args()

    roots: List[Path] = []
    if args.info_root:
        roots.append(BASE_DIR / args.info_root)
    if args.flash:
        roots.append(
            BASE_DIR
            / "result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3-flash-preview"
        )
    if args.lite:
        roots.append(
            BASE_DIR
            / "result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3.1-flash-lite-preview"
        )
    if not roots:
        roots.append(
            BASE_DIR
            / "result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3.1-pro-preview"
        )

    tex_dir = Path(args.tex_dir).expanduser().resolve() if args.tex_dir else DEFAULT_TEX_DIR
    stem = args.tex_stem or DEFAULT_TEX_STEM
    extra = _sanitize_tex_suffix(args.tex_suffix) if args.tex_suffix else ""

    if args.output_tex and len(roots) != 1:
        ap.error("--output-tex requires exactly one input root (use --info-root only).")

    seen = set()
    for r in roots:
        r = r.resolve()
        if r in seen:
            continue
        seen.add(r)

        quiet = bool(
            args.no_stdout and (args.write_tex or bool(args.output_tex))
        )
        ok, _report, latex_text, def_suf = aggregate_one_model(r, quiet=quiet)

        if args.output_tex:
            if not ok:
                print(
                    f"[skip] --output-tex not written (missing data): {r}",
                    file=sys.stderr,
                )
                continue
            out_path = Path(args.output_tex).expanduser().resolve()
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(latex_text, encoding="utf-8")
            if not quiet:
                print(f"Wrote LaTeX fragment: {out_path}", file=sys.stderr)
            continue

        if args.write_tex and ok:
            if extra:
                name = f"{stem}_{def_suf}_{extra}.tex"
            else:
                name = f"{stem}_{def_suf}.tex"
            out_path = tex_dir / name
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(latex_text, encoding="utf-8")
            if not quiet:
                print(f"Wrote LaTeX fragment: {out_path}", file=sys.stderr)
        elif args.write_tex and not ok:
            print(f"[skip] no LaTeX written for {r}", file=sys.stderr)


if __name__ == "__main__":
    main()
