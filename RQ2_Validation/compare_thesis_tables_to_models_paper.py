#!/usr/bin/env python3
"""
Compare per-predicate counts: result/thesis/RQ1_TestVsNoTest/tables vs
Models-2026---Alloy-Synthesis/tables/results-arepair-*-tests.tex

Usage (repo root):
  python scripts/thesis/RQ1_TestVsNoTest/compare_thesis_tables_to_models_paper.py
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PAPER = REPO / "Models-2026---Alloy-Synthesis" / "tables"
THESIS = REPO / "result" / "thesis" / "RQ1_TestVsNoTest" / "tables"

MODELS = [
    ("pro", "gemini-3.1-pro-preview"),
    ("flash", "gemini-3-flash-preview"),
    ("lite", "gemini-3.1-flash-lite-preview"),
]


def parse_paper_simple_rows(path: Path) -> dict[str, list[int]]:
    """Paper table: pred & N & 24 ints (3 models × 8)."""
    text = path.read_text(encoding="utf-8")
    rows: dict[str, list[int]] = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("\\rowcolor"):
            i += 1
            continue
        if "&" not in line or line.startswith("%"):
            i += 1
            continue
        if "\\textbf{Totals}" in line or "Totals" in line and "\\textbf" in line:
            i += 1
            continue
        if "\\midrule" in line or "\\toprule" in line or "\\bottomrule" in line:
            i += 1
            continue
        parts = [p.strip().rstrip("\\").strip() for p in line.split("&")]
        if len(parts) < 3:
            i += 1
            continue
        pred = parts[0].strip()
        if not pred or pred.startswith("\\"):
            i += 1
            continue
        # first col might be "student-Sorted " with spaces
        pred = pred.split()[0] if pred.split() else pred
        try:
            nums = []
            for x in parts[1:]:
                x = x.split()[0] if x.split() else x
                nums.append(int(x))
        except ValueError:
            i += 1
            continue
        if len(nums) < 25:  # N + 24
            i += 1
            continue
        # nums[0] is N; next 24 are model blocks
        rows[pred] = nums
        i += 1
    return rows


def split_paper_by_model(nums: list[int]) -> tuple[list[int], list[int], list[int]]:
    """nums = [N, pro×8, flash×8, lite×8]."""
    assert len(nums) >= 25
    n, a, b, c = nums[0], nums[1:9], nums[9:17], nums[17:25]
    assert len(a) == len(b) == len(c) == 8
    return a, b, c


def parse_thesis_e2a(path: Path) -> dict[str, list[int]]:
    """Thesis E2A: pred & wt_cor & wt_syn & wt_sem & nt_cor & nt_syn & nt_sem (6 ints)."""
    rows: dict[str, list[int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "&" not in line or "\\textbf" in line:
            continue
        parts = [p.strip().rstrip("\\").strip() for p in line.split("&")]
        pred = parts[0].strip()
        if not pred or pred.startswith("\\"):
            continue
        try:
            nums = [int((x.split() or [x])[0]) for x in parts[1:]]
        except ValueError:
            continue
        if len(nums) != 6:
            continue
        rows[pred] = nums
    return rows


def parse_thesis_a2a_colored(path: Path) -> dict[str, list[int]]:
    """Extract 8 ints per row (Cor/Sem/Syn/Rep × WT/NT) from textcolor rows."""

    def cell_int(cell: str) -> int:
        m = re.search(r"\\textcolor\{(?:blue|red)\}\{(\d+)", cell)
        if m:
            return int(m.group(1))
        m2 = re.search(r"\{(\d+)", cell)
        if m2:
            return int(m2.group(1))
        raise ValueError(cell)

    rows: dict[str, list[int]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if "&" not in line or "\\textbf{Totals}" in line or "\\midrule" in line:
            continue
        parts = [p.strip() for p in line.split("&")]
        if len(parts) < 10:
            continue
        pred = parts[0].strip()
        if not pred or not pred[0].isalpha():
            continue
        cells = parts[2:10]  # after name & Unique(10)
        if len(cells) != 8:
            continue
        try:
            nums = [cell_int(c) for c in cells]
        except ValueError:
            continue
        rows[pred] = nums
    return rows


def css6(paper8: list[int]) -> list[int]:
    """Paper order: Cor_wt, Cor_nt, Syn_wt, Syn_nt, Sem_wt, Sem_nt, Rep_wt, Rep_nt"""
    return paper8[:6]


def thesis_e2a_to_paper_order(t6: list[int]) -> list[int]:
    """
    Thesis file order: WT Cor, Syn, Sem then NT Cor, Syn, Sem
    Paper order: Cor WT/NT, Syn WT/NT, Sem WT/NT
    """
    wt_c, wt_sy, wt_se, nt_c, nt_sy, nt_se = t6
    return [wt_c, nt_c, wt_sy, nt_sy, wt_se, nt_se]


def main() -> None:
    paper_e2a = parse_paper_simple_rows(PAPER / "results-arepair-eng-2-alloy-tests.tex")
    paper_a2a = parse_paper_simple_rows(PAPER / "results-arepair-alloy-2-alloy-tests.tex")

    e2a_paths = {
        key: THESIS / f"with_vs_no_test_by_predicate_{mid}.tex" for key, mid in MODELS
    }
    a2a_paths = {
        key: THESIS / f"with_vs_no_test_alloy2alloy_by_predicate_{mid}.tex"
        for key, mid in MODELS
    }

    preds = sorted(set(paper_e2a.keys()) | set(paper_a2a.keys()))

    print("=== E2A (English→Alloy): thesis 6 numbers vs paper [Cor/Syn/Sem WT/NT] (Rep ignored) ===\n")
    e2a_mismatches = []
    for pred in preds:
        if pred not in paper_e2a:
            print(f"[skip] {pred}: missing in paper E2A")
            continue
        pa, pb, pc = split_paper_by_model(paper_e2a[pred])
        for key, thesis_path in e2a_paths.items():
            paper_block = {"pro": pa, "flash": pb, "lite": pc}[key]
            t = parse_thesis_e2a(thesis_path)
            if pred not in t:
                e2a_mismatches.append((pred, key, "missing thesis row"))
                continue
            t6 = thesis_e2a_to_paper_order(t[pred])
            p6 = css6(paper_block)
            if t6 != p6:
                e2a_mismatches.append((pred, key, f"thesis {t6} vs paper {p6}"))

    if not e2a_mismatches:
        print("All predicates × all 3 models: EXACT match (Cor/Syn/Sem only).\n")
    else:
        print(f"Mismatches: {len(e2a_mismatches)}\n")
        for pred, key, msg in e2a_mismatches:
            print(f"  {pred}  [{key}]  {msg}")

    print("\n=== A2A (Alloy→Alloy): thesis 8 numbers vs paper (incl. Rep) ===\n")
    a2a_mismatches = []
    for pred in preds:
        if pred not in paper_a2a:
            print(f"[skip] {pred}: missing in paper A2A")
            continue
        pa, pb, pc = split_paper_by_model(paper_a2a[pred])
        for key, thesis_path in a2a_paths.items():
            paper_block = {"pro": pa, "flash": pb, "lite": pc}[key]
            t = parse_thesis_a2a_colored(thesis_path)
            if pred not in t:
                a2a_mismatches.append((pred, key, "missing thesis row"))
                continue
            t8 = t[pred]
            if t8 != paper_block:
                a2a_mismatches.append((pred, key, f"thesis {t8} vs paper {paper_block}"))

    if not a2a_mismatches:
        print("All predicates × all 3 models: EXACT match (8 columns).\n")
    else:
        print(f"Mismatches (full 8 cols, incl. Rep): {len(a2a_mismatches)}\n")
        for pred, key, msg in a2a_mismatches:
            print(f"  {pred}  [{key}]  {msg}")

    # Cor/Syn/Sem only (ignore Rep) — if only Rep differs, ARepair re-runs won't change CSS counts
    a2a_css_mismatches = []
    for pred in preds:
        if pred not in paper_a2a:
            continue
        pa, pb, pc = split_paper_by_model(paper_a2a[pred])
        for key, thesis_path in a2a_paths.items():
            paper_block = {"pro": pa, "flash": pb, "lite": pc}[key]
            t = parse_thesis_a2a_colored(thesis_path)
            if pred not in t:
                continue
            if t[pred][:6] != paper_block[:6]:
                a2a_css_mismatches.append(
                    (pred, key, f"thesis {t[pred][:6]} vs paper {paper_block[:6]}")
                )

    print("\n=== A2A Cor/Syn/Sem only (first 6 columns, Rep ignored) ===\n")
    if not a2a_css_mismatches:
        print("All predicates × all 3 models: EXACT match.\n")
    else:
        print(f"Mismatches: {len(a2a_css_mismatches)}\n")
        for pred, key, msg in a2a_css_mismatches:
            print(f"  {pred}  [{key}]  {msg}")

    print("---")
    print(
        "Interpretation: E2A tables align with Models-2026. A2A Rep differences mean "
        "repairability counts differ for those cells; re-running ARepair only matters if "
        "you need Rep columns to match the paper — Cor/Syn/Sem already match for A2A where "
        "only Rep differed."
    )


if __name__ == "__main__":
    main()
