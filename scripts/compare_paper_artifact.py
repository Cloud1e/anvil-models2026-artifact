#!/usr/bin/env python3
"""Extract paper/artifact tables and diff them cell-by-cell.

This script is intentionally separate from the RQ pipelines. It reads existing
raw logs/results, writes human-readable wide CSVs that mirror the paper tables,
then flattens those tables internally for a machine-checkable diff_report.csv.
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


MODELS = [
    ("pro", "gemini-3.1-pro-preview"),
    ("flash", "gemini-3-flash-preview"),
    ("lite", "gemini-3.1-flash-lite-preview"),
]

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

RQ1_COLUMNS = [
    f"{task}/{model}/{metric}"
    for task in ("E2A", "A2A")
    for model in ("pro", "flash", "lite")
    for metric in ("Unique", "Cor", "Syn", "Sem")
]

RQ2_COLUMNS = [
    "N",
    *[
        f"{model}/{metric}/{cfg}"
        for model in ("pro", "flash", "lite")
        for metric in ("Cor", "Syn", "Sem", "Rep")
        for cfg in ("WT", "NT")
    ],
]

RQ3_COLUMNS = [
    "original/Cor",
    "original/Syn",
    "original/Sem",
    *[
        f"{model}/{metric}"
        for model in ("pro", "flash", "lite")
        for metric in ("LLM_Cor", "LLM_Syn", "LLM_Sem", "OrigRep", "LLMRep")
    ],
]


def artifact_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir():
            return parent
    raise RuntimeError("Could not locate anvil-artifact root")


ROOT = artifact_root()
PAPER_TABLES = ROOT.parent / "Models-2026---Alloy-Synthesis" / "tables"


def read_wide_csv(path: Path) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    rows: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames or "row" not in reader.fieldnames:
            raise ValueError(f"Wide CSV is missing a row column: {path}")
        columns = [c for c in reader.fieldnames if c != "row"]
        for record in reader:
            row_id = record.get("row", "")
            if not row_id:
                continue
            order.append(row_id)
            rows[row_id] = {col: record.get(col, "") for col in columns}
    return rows, order


def paper_table_path(table_name: str, fallback_csv: Path) -> Optional[Path]:
    table = PAPER_TABLES / f"{table_name}.tex"
    if table.is_file():
        return table
    if fallback_csv.is_file():
        return None
    raise FileNotFoundError(
        f"Could not find external paper table {table} or artifact-local fallback {fallback_csv}"
    )


def strip_latex(cell: str) -> str:
    cell = cell.strip().rstrip("\\").strip()
    # Expand common wrappers one level at a time.
    for _ in range(5):
        new = re.sub(r"\\(?:textbf|Intro|emph)\{([^{}]*)\}", r"\1", cell)
        if new == cell:
            break
        cell = new
    cell = cell.replace("\\cmark", "1").replace("\\xmark", "0")
    cell = re.sub(r"\\[a-zA-Z]+", "", cell)
    cell = cell.replace("{", "").replace("}", "")
    return cell.strip()


def split_latex_cells(row: str) -> List[str]:
    cells: List[str] = []
    for raw in row.split("&"):
        raw = raw.strip().rstrip("\\").strip()
        m = re.fullmatch(r"\\multicolumn\{(\d+)\}\{[^{}]*\}\{(.+)\}", raw)
        if m:
            cells.extend([strip_latex(m.group(2))] * int(m.group(1)))
        else:
            cells.append(strip_latex(raw))
    return cells


def iter_latex_data_rows(path: Path) -> Iterable[List[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line.startswith("%") or line.startswith("\\rowcolor"):
            i += 1
            continue
        if "&" not in line:
            i += 1
            continue
        row = line
        while "\\\\" not in row and i + 1 < len(lines):
            i += 1
            row += " " + lines[i].strip()
        i += 1
        cells = split_latex_cells(row)
        if not cells:
            continue
        first = cells[0].strip()
        if not first or first.startswith("\\") or first in {"Property", "Predicate"}:
            continue
        if first == "":
            continue
        yield cells


def row_id_from_uid(uid: str, suffixes: Tuple[str, ...]) -> str:
    base = uid
    for suffix in suffixes:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base.replace("_", "-", 1)


def write_wide(path: Path, rows: Dict[str, Dict[str, str]], row_order: List[str], columns: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["row"] + columns)
        for row_id in row_order:
            vals = rows.get(row_id, {})
            writer.writerow([row_id] + [vals.get(col, "") for col in columns])


def flatten(rq: str, table: str, rows: Dict[str, Dict[str, str]], row_order: List[str], columns: List[str]) -> List[Dict[str, str]]:
    out = []
    for row_id in row_order:
        vals = rows.get(row_id, {})
        for col in columns:
            out.append(
                {
                    "rq": rq,
                    "table_name": table,
                    "row_id": row_id,
                    "column_name": col,
                    "value": vals.get(col, ""),
                }
            )
    return out


def write_long(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def parse_rq1_paper() -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    fallback = ROOT / "RQ1_Generation" / "comparison" / "paper_results-synthesis.csv"
    table = paper_table_path("results-synthesis", fallback)
    if table is None:
        return read_wide_csv(fallback)
    rows: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for cells in iter_latex_data_rows(table):
        if len(cells) != 19:
            continue
        prop = cells[0]
        try:
            nums = [int(x) for x in cells[1:]]
        except ValueError:
            continue
        order.append(prop)
        vals: Dict[str, str] = {}
        idx = 0
        for task in ("E2A", "A2A"):
            for model in ("pro", "flash", "lite"):
                cor, syn, sem = nums[idx : idx + 3]
                idx += 3
                vals[f"{task}/{model}/Unique"] = "20"
                vals[f"{task}/{model}/Cor"] = str(cor)
                vals[f"{task}/{model}/Syn"] = str(syn)
                vals[f"{task}/{model}/Sem"] = str(sem)
        rows[prop] = vals
    return rows, order


def latest_rq1_log() -> Path:
    logs = sorted((ROOT / "RQ1_Generation" / "logs").glob("rq1_overnight_*.log"))
    if not logs:
        fallback = ROOT / "RQ1_Generation" / "comparison" / "artifact_results-synthesis.csv"
        if fallback.is_file():
            return fallback
        raise FileNotFoundError(
            "No RQ1 overnight log found under RQ1_Generation/logs and no "
            "RQ1_Generation/comparison/artifact_results-synthesis.csv fallback exists"
        )
    return logs[-1]


def parse_rq1_artifact() -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    source = latest_rq1_log()
    if source.name == "artifact_results-synthesis.csv":
        return read_wide_csv(source)
    lines = source.read_text(encoding="utf-8", errors="ignore").splitlines()
    model_key = {slug: key for key, slug in MODELS}
    current_model = None
    current_task = None
    rows: Dict[str, Dict[str, str]] = defaultdict(dict)
    order: List[str] = []
    in_summary = False
    for line in lines:
        m = re.search(r"RQ1 model=([^ ]+)", line)
        if m:
            current_model = model_key.get(m.group(1))
        if "Result GEMINI - EnglishToAlloy" in line:
            current_task = "E2A"
        elif "Result GEMINI - AlloyToAlloy" in line:
            current_task = "A2A"
        if "Predicate & Unique & Cor & Syn & Sem" in line:
            in_summary = True
            continue
        if in_summary and "\\end{tabular}" in line:
            in_summary = False
            continue
        if not in_summary or not current_model or not current_task:
            continue
        cells = split_latex_cells(line)
        if len(cells) != 5:
            continue
        prop = cells[0]
        try:
            unique, cor, syn, sem = [int(x) for x in cells[1:]]
        except ValueError:
            continue
        if prop not in rows:
            order.append(prop)
        prefix = f"{current_task}/{current_model}"
        rows[prop][f"{prefix}/Unique"] = str(unique)
        rows[prop][f"{prefix}/Cor"] = str(cor)
        rows[prop][f"{prefix}/Syn"] = str(syn)
        rows[prop][f"{prefix}/Sem"] = str(sem)
    return dict(rows), order


def parse_result_file_to_pred_counts(path: Path, model_name: str) -> Dict[str, Dict[str, int]]:
    out: Dict[str, Dict[str, int]] = {}
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
        elif ":" in line:
            parts = line.split(":", 1)
            if len(parts) == 2 and i + 1 < len(lines):
                pred_name = parts[0].strip()
                next_line = lines[i + 1].strip()
                if next_line in ("Correct", "Syntax Error", "Wrong"):
                    status = next_line
                    i += 1
        if pred_name and status:
            out.setdefault(pred_name, {"Correct": 0, "Syntax Error": 0, "Wrong": 0})
            out[pred_name][status] += 1
        i += 1
    if is_single and single_pred_name and single_pred_name not in out:
        summary = {"Correct": None, "Syntax Error": None, "Wrong": None}
        for line in lines:
            s = line.strip()
            for key in list(summary):
                if s.startswith(f"{key}:"):
                    try:
                        summary[key] = int(s.split(":", 1)[1].strip())
                    except ValueError:
                        pass
        if all(v is not None for v in summary.values()):
            out[single_pred_name] = {k: int(v) for k, v in summary.items() if v is not None}
    return out


def load_repair_counts(path: Path) -> Dict[str, int]:
    counts: Dict[str, int] = defaultdict(int)
    if not path.is_file():
        return counts
    data = json.loads(path.read_text(encoding="utf-8"))
    for item in data:
        if item.get("status") in ("SUCCESS", "PARTIAL"):
            uid = item.get("unique_id", "")
            parts = uid.rsplit("_", 1)
            if len(parts) == 2:
                counts[parts[0].replace("_", "-", 1)] += 1
    return dict(counts)


def parse_rq2_paper(table_name: str) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    fallback = ROOT / "RQ2_Validation" / "comparison" / f"paper_{table_name}.csv"
    path = paper_table_path(table_name, fallback)
    if path is None:
        return read_wide_csv(fallback)
    rows: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for cells in iter_latex_data_rows(path):
        if len(cells) != 26:
            continue
        row_id = "Totals" if cells[0] == "Totals" else cells[0]
        try:
            nums = [int(x) for x in cells[1:]]
        except ValueError:
            continue
        vals = {"N": str(nums[0])}
        idx = 1
        for model in ("pro", "flash", "lite"):
            for metric in ("Cor", "Syn", "Sem", "Rep"):
                vals[f"{model}/{metric}/WT"] = str(nums[idx])
                vals[f"{model}/{metric}/NT"] = str(nums[idx + 1])
                idx += 2
        order.append(row_id)
        rows[row_id] = vals
    return rows, order


def parse_rq2_artifact(task: str) -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    base = ROOT / "result" / "Gemini" / "RQ2_Validation" / task
    rows: Dict[str, Dict[str, str]] = {}
    for model_key, model_slug in MODELS:
        for cfg, cfg_key in (("WithTest", "WT"), ("NoTest", "NT")):
            alloy_dir = base / model_slug / cfg / "Alloy"
            repair_json = base / model_slug / cfg / "RepairResults" / "repair_results.json"
            repair_counts = load_repair_counts(repair_json)
            for bench, preds in MODEL_PREDICATES.items():
                counts = parse_result_file_to_pred_counts(alloy_dir / f"{bench}.txt", bench)
                for pred in preds:
                    row_id = f"{bench}-{pred}"
                    c = counts.get(pred, {"Correct": 0, "Syntax Error": 0, "Wrong": 0})
                    rows.setdefault(row_id, {})["N"] = "10"
                    rows[row_id][f"{model_key}/Cor/{cfg_key}"] = str(c.get("Correct", 0))
                    rows[row_id][f"{model_key}/Syn/{cfg_key}"] = str(c.get("Syntax Error", 0))
                    rows[row_id][f"{model_key}/Sem/{cfg_key}"] = str(c.get("Wrong", 0))
                    rows[row_id][f"{model_key}/Rep/{cfg_key}"] = str(repair_counts.get(row_id, 0))
    order = [f"{bench}-{pred}" for bench, preds in MODEL_PREDICATES.items() for pred in preds]
    totals = {"N": str(sum(int(rows[r]["N"]) for r in order))}
    for col in RQ2_COLUMNS:
        if col == "N":
            continue
        totals[col] = str(sum(int(rows[r].get(col, "0")) for r in order))
    rows["Totals"] = totals
    order.append("Totals")
    return rows, order


def parse_rq3_paper() -> Tuple[Dict[str, Dict[str, str]], List[str]]:
    fallback = ROOT / "RQ3_Repair" / "comparison" / "paper_results-arepair-faulty-alloy-2-alloy.csv"
    table = paper_table_path("results-arepair-faulty-alloy-2-alloy", fallback)
    if table is None:
        return read_wide_csv(fallback)
    rows: Dict[str, Dict[str, str]] = {}
    order: List[str] = []
    for cells in iter_latex_data_rows(table):
        if len(cells) != 19:
            continue
        row_id = "Total" if cells[0] == "Total" else cells[0]
        vals: Dict[str, str] = {}
        idx = 1
        for col in ("original/Cor", "original/Syn", "original/Sem"):
            vals[col] = cells[idx]
            idx += 1
        for model in ("pro", "flash", "lite"):
            for metric in ("LLM_Cor", "LLM_Syn", "LLM_Sem", "OrigRep", "LLMRep"):
                vals[f"{model}/{metric}"] = cells[idx]
                idx += 1
        order.append(row_id)
        rows[row_id] = vals
    return rows, order


def rq3_paths(model_slug: str) -> Path:
    return ROOT / "result" / "Gemini" / "RQ3_Repair" / "FaultyRewrite" / model_slug / "ARepair_FaultyRewrite"


def load_rq3_classification(model_slug: str) -> List[dict]:
    path = rq3_paths(model_slug) / "classification.json"
    return json.loads(path.read_text(encoding="utf-8"))["results"]


def load_rq3_repair_statuses(model_slug: str, kind: str) -> Dict[str, str]:
    path = rq3_paths(model_slug) / kind / "repair_results.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {item.get("unique_id", ""): item.get("status", "") for item in data}


def parse_rq3_artifact(row_order: List[str]) -> Tuple[Dict[str, Dict[str, str]], List[Dict[str, str]]]:
    rows: Dict[str, Dict[str, str]] = {}
    diagnostics: List[Dict[str, str]] = []
    original_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"Cor": 0, "Syn": 0, "Sem": 0})
    original_sem_ids: Dict[str, set] = defaultdict(set)
    first_model_slug = MODELS[0][1]
    for item in load_rq3_classification(first_model_slug):
        if item.get("kind") != "original":
            continue
        row_id = f"{item['model_name']}-{item['predicate_name']}"
        result = item.get("result")
        if result in ("Cor", "Syn", "Sem"):
            original_counts[row_id][result] += 1
            if result == "Sem":
                original_sem_ids[row_id].add(item["unique_id"])

    original_repair_by_model: Dict[str, Dict[str, int]] = {}
    for model_key, model_slug in MODELS:
        statuses = load_rq3_repair_statuses(model_slug, "RepairResultsOriginal")
        counts: Dict[str, int] = defaultdict(int)
        for uid, status in statuses.items():
            if status in ("SUCCESS", "PARTIAL"):
                counts[row_id_from_uid(uid, ("_original",))] += 1
        original_repair_by_model[model_key] = dict(counts)

    llm_counts_by_model: Dict[str, Dict[str, Dict[str, int]]] = {}
    llm_sem_ids_by_model: Dict[str, Dict[str, set]] = {}
    llm_success_by_model: Dict[str, Dict[str, int]] = {}
    llm_success_ids_by_model: Dict[str, Dict[str, set]] = {}
    for model_key, model_slug in MODELS:
        counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"Cor": 0, "Syn": 0, "Sem": 0})
        sem_ids: Dict[str, set] = defaultdict(set)
        for item in load_rq3_classification(model_slug):
            if item.get("kind") != "llm":
                continue
            row_id = f"{item['model_name']}-{item['predicate_name']}"
            result = item.get("result")
            if result in ("Cor", "Syn", "Sem"):
                counts[row_id][result] += 1
                if result == "Sem":
                    sem_ids[row_id].add(item["unique_id"])
        successes: Dict[str, int] = defaultdict(int)
        success_ids: Dict[str, set] = defaultdict(set)
        for uid, status in load_rq3_repair_statuses(model_slug, "RepairResultsLLM").items():
            if status in ("SUCCESS", "PARTIAL"):
                row_id = row_id_from_uid(uid, ("_llm_0", "_llm_1", "_llm_2", "_llm_3", "_llm_4", "_llm_5", "_llm_6", "_llm_7", "_llm_8", "_llm_9"))
                # Safer fallback for arbitrary indexes.
                row_id = re.sub(r"_llm_\d+$", "", uid).replace("_", "-", 1)
                successes[row_id] += 1
                success_ids[row_id].add(uid)
        llm_counts_by_model[model_key] = dict(counts)
        llm_sem_ids_by_model[model_key] = dict(sem_ids)
        llm_success_by_model[model_key] = dict(successes)
        llm_success_ids_by_model[model_key] = dict(success_ids)

    for row_id in row_order:
        vals: Dict[str, str] = {}
        if row_id == "Total":
            oc = {
                k: sum(v[k] for v in original_counts.values())
                for k in ("Cor", "Syn", "Sem")
            }
            vals["original/Cor"] = str(oc["Cor"])
            vals["original/Syn"] = str(oc["Syn"])
            vals["original/Sem"] = str(oc["Sem"])
        elif row_id in original_counts:
            vals["original/Cor"] = str(original_counts[row_id]["Cor"])
            vals["original/Syn"] = str(original_counts[row_id]["Syn"])
            vals["original/Sem"] = str(original_counts[row_id]["Sem"])
        else:
            vals["original/Cor"] = vals["original/Syn"] = vals["original/Sem"] = "NA"

        for model_key, _model_slug in MODELS:
            if row_id == "Total":
                cor = sum(v.get("Cor", 0) for v in llm_counts_by_model[model_key].values())
                syn = sum(v.get("Syn", 0) for v in llm_counts_by_model[model_key].values())
                sem = sum(v.get("Sem", 0) for v in llm_counts_by_model[model_key].values())
                orig_success = sum(original_repair_by_model[model_key].values())
                orig_total = sum(v["Sem"] for v in original_counts.values())
                llm_success = sum(llm_success_by_model[model_key].values())
                vals[f"{model_key}/LLM_Cor"] = str(cor)
                vals[f"{model_key}/LLM_Syn"] = str(syn)
                vals[f"{model_key}/LLM_Sem"] = str(sem)
                vals[f"{model_key}/OrigRep"] = f"{orig_success}/{orig_total}"
                vals[f"{model_key}/LLMRep"] = f"{llm_success}/{sem}"
            elif row_id in llm_counts_by_model[model_key]:
                c = llm_counts_by_model[model_key][row_id]
                sem_total = c.get("Sem", 0)
                vals[f"{model_key}/LLM_Cor"] = str(c.get("Cor", 0))
                vals[f"{model_key}/LLM_Syn"] = str(c.get("Syn", 0))
                vals[f"{model_key}/LLM_Sem"] = str(sem_total)
                vals[f"{model_key}/OrigRep"] = f"{original_repair_by_model[model_key].get(row_id, 0)}/{original_counts[row_id]['Sem']}"
                vals[f"{model_key}/LLMRep"] = f"{llm_success_by_model[model_key].get(row_id, 0)}/{sem_total}"
            else:
                for metric in ("LLM_Cor", "LLM_Syn", "LLM_Sem", "OrigRep", "LLMRep"):
                    vals[f"{model_key}/{metric}"] = "NA"
        rows[row_id] = vals

    for model_key, _model_slug in MODELS:
        for row_id in sorted(llm_counts_by_model[model_key]):
            sem_ids = llm_sem_ids_by_model[model_key].get(row_id, set())
            success_ids = llm_success_ids_by_model[model_key].get(row_id, set())
            outside = sorted(success_ids - sem_ids)
            diagnostics.append(
                {
                    "model": model_key,
                    "row_id": row_id,
                    "llm_cor": str(llm_counts_by_model[model_key][row_id].get("Cor", 0)),
                    "llm_syn": str(llm_counts_by_model[model_key][row_id].get("Syn", 0)),
                    "llm_sem": str(llm_counts_by_model[model_key][row_id].get("Sem", 0)),
                    "paper_table_successes_all_rewrites": str(len(success_ids)),
                    "sem_only_successes": str(len(success_ids & sem_ids)),
                    "successes_outside_sem": str(len(outside)),
                    "success_ids_outside_sem": ";".join(outside),
                }
            )
        total_success = sum(len(v) for v in llm_success_ids_by_model[model_key].values())
        total_sem_success = sum(
            len(llm_success_ids_by_model[model_key].get(row_id, set()) & llm_sem_ids_by_model[model_key].get(row_id, set()))
            for row_id in llm_counts_by_model[model_key]
        )
        diagnostics.append(
            {
                "model": model_key,
                "row_id": "Total",
                "llm_cor": str(sum(v.get("Cor", 0) for v in llm_counts_by_model[model_key].values())),
                "llm_syn": str(sum(v.get("Syn", 0) for v in llm_counts_by_model[model_key].values())),
                "llm_sem": str(sum(v.get("Sem", 0) for v in llm_counts_by_model[model_key].values())),
                "paper_table_successes_all_rewrites": str(total_success),
                "sem_only_successes": str(total_sem_success),
                "successes_outside_sem": str(total_success - total_sem_success),
                "success_ids_outside_sem": "",
            }
        )
    return rows, diagnostics


def compare_rows(rq: str, paper_long: List[Dict[str, str]], artifact_long: List[Dict[str, str]]) -> List[Dict[str, str]]:
    art_map = {
        (r["table_name"], r["row_id"], r["column_name"]): r["value"]
        for r in artifact_long
    }
    diff = []
    for p in paper_long:
        key = (p["table_name"], p["row_id"], p["column_name"])
        artifact_value = art_map.get(key, "")
        paper_value = p["value"]
        diff.append(
            {
                "rq": rq,
                "table_name": p["table_name"],
                "row_id": p["row_id"],
                "column_name": p["column_name"],
                "paper_value": paper_value,
                "artifact_value": artifact_value,
                "match": str(paper_value == artifact_value).lower(),
            }
        )
    return diff


def process_rq(rq: str, rq_dir: Path, tables: List[Tuple[str, Dict[str, Dict[str, str]], Dict[str, Dict[str, str]], List[str], List[str]]]) -> dict:
    comparison = rq_dir / "comparison"
    comparison.mkdir(parents=True, exist_ok=True)
    paper_long: List[Dict[str, str]] = []
    artifact_long: List[Dict[str, str]] = []
    for table_name, paper_rows, artifact_rows, row_order, columns in tables:
        write_wide(comparison / f"paper_{table_name}.csv", paper_rows, row_order, columns)
        write_wide(comparison / f"artifact_{table_name}.csv", artifact_rows, row_order, columns)
        paper_long.extend(flatten(rq, table_name, paper_rows, row_order, columns))
        artifact_long.extend(flatten(rq, table_name, artifact_rows, row_order, columns))

    write_long(comparison / "paper_ground_truth.csv", paper_long, ["rq", "table_name", "row_id", "column_name", "value"])
    write_long(comparison / "extracted_artifact_values.csv", artifact_long, ["rq", "table_name", "row_id", "column_name", "value"])
    diff = compare_rows(rq, paper_long, artifact_long)
    write_long(
        comparison / "diff_report.csv",
        diff,
        ["rq", "table_name", "row_id", "column_name", "paper_value", "artifact_value", "match"],
    )
    mismatches = [r for r in diff if r["match"] != "true"]
    summary = {
        "rq": rq,
        "total": len(diff),
        "matches": len(diff) - len(mismatches),
        "mismatches": len(mismatches),
        "mismatch_rows": mismatches,
        "diff_csv": str((comparison / "diff_report.csv").relative_to(ROOT)),
    }
    (comparison / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    rq1_paper, rq1_order = parse_rq1_paper()
    rq1_artifact, _ = parse_rq1_artifact()
    rq1_summary = process_rq(
        "RQ1",
        ROOT / "RQ1_Generation",
        [("results-synthesis", rq1_paper, rq1_artifact, rq1_order, RQ1_COLUMNS)],
    )

    rq2_tables = []
    for task, table_name in (
        ("E2A", "results-arepair-eng-2-alloy-tests"),
        ("A2A", "results-arepair-alloy-2-alloy-tests"),
    ):
        paper, order = parse_rq2_paper(table_name)
        artifact, _ = parse_rq2_artifact(task)
        rq2_tables.append((table_name, paper, artifact, order, RQ2_COLUMNS))
    rq2_summary = process_rq("RQ2", ROOT / "RQ2_Validation", rq2_tables)

    rq3_paper, rq3_order = parse_rq3_paper()
    rq3_artifact, diagnostics = parse_rq3_artifact(rq3_order)
    rq3_summary = process_rq(
        "RQ3",
        ROOT / "RQ3_Repair",
        [("results-arepair-faulty-alloy-2-alloy", rq3_paper, rq3_artifact, rq3_order, RQ3_COLUMNS)],
    )
    write_long(
        ROOT / "RQ3_Repair" / "comparison" / "repair_definition_diagnostic.csv",
        diagnostics,
        [
            "model",
            "row_id",
            "llm_cor",
            "llm_syn",
            "llm_sem",
            "paper_table_successes_all_rewrites",
            "sem_only_successes",
            "successes_outside_sem",
            "success_ids_outside_sem",
        ],
    )

    all_diff = []
    for rq_dir in ("RQ1_Generation", "RQ2_Validation", "RQ3_Repair"):
        path = ROOT / rq_dir / "comparison" / "diff_report.csv"
        with path.open(newline="", encoding="utf-8") as f:
            all_diff.extend(csv.DictReader(f))
    orch = ROOT / "logs" / "orchestration"
    orch.mkdir(parents=True, exist_ok=True)
    write_long(
        orch / "paper_artifact_diff_latest.csv",
        all_diff,
        ["rq", "table_name", "row_id", "column_name", "paper_value", "artifact_value", "match"],
    )
    all_mismatches = [r for r in all_diff if r["match"] != "true"]
    combined = {
        "total": len(all_diff),
        "matches": len(all_diff) - len(all_mismatches),
        "mismatches": all_mismatches,
        "by_rq": {
            "RQ1": rq1_summary,
            "RQ2": rq2_summary,
            "RQ3": rq3_summary,
        },
        "combined_diff_csv": str((orch / "paper_artifact_diff_latest.csv").relative_to(ROOT)),
    }
    (orch / "paper_artifact_diff_latest_summary.json").write_text(json.dumps(combined, indent=2), encoding="utf-8")

    print("Paper/artifact diff complete.")
    print(f"Combined: {combined['matches']}/{combined['total']} matched; mismatches={len(all_mismatches)}")
    for rq, summary in combined["by_rq"].items():
        print(f"{rq}: {summary['matches']}/{summary['total']} matched; mismatches={summary['mismatches']}")
    if all_mismatches:
        print("Mismatches:")
        for row in all_mismatches:
            print(
                f"  {row['rq']} {row['table_name']} {row['row_id']} {row['column_name']}: "
                f"paper={row['paper_value']} artifact={row['artifact_value']}"
            )


if __name__ == "__main__":
    main()
