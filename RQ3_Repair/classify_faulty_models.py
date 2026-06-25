#!/usr/bin/env python
"""
Classify faulty models (original + LLM-rewritten) as Cor / Syn / Sem before ARepair.

Thesis mode (only mode):
  - **Primary:** run Java ``Example --check-one`` on the candidate model. This is the
    historical RQ3 classification source used by the stored paper data.
  - **Diagnostic:** merge candidate model with its test suite and run Java
    ``Rq3ParallelTestSuiteOracle``.
  - **Reference (per predicate):** bounded ``check { P <=> P__cand }`` — gold predicate from
    ``ARepair/experiments/models/<model>.als`` vs faulty predicate body in the case's ``model_path``,
    via ``Example --faulty-pred-equiv``. This is **pred-vs-pred** equivalence, not whole-file ``--check-one``.

Compares Cor/Syn/Sem from check-one vs diagnostics; every 10 cases prints cumulative agreement count.

Requires ``test_suite_path`` in repair_info for every entry; entries without a valid test suite file are skipped.

Writes:
  - <info-root>/classification.json
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



# classify_faulty_models.py -> RQ2_FaultyRewrite_ARepair -> thesis -> scripts -> repo root
REPO_ROOT = _artifact_repo_root()


def _load_env() -> None:
    """Load .env from project root if present (KEY=VALUE per line, no quotes)."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip("'\"")
            if k and k not in os.environ:
                os.environ[k] = v


def _ensure_java_build() -> Optional[str]:
    """Ensure Maven package ran once; returns error string or None."""
    marker = REPO_ROOT / "target" / ".example_built"
    if marker.exists():
        return None
    prep = subprocess.run(
        ["mvn", "-q", "-DskipTests", "package"],
        cwd=REPO_ROOT,
        timeout=600,
    )
    if prep.returncode != 0:
        return "mvn package failed (see Maven output)"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("ok", encoding="utf-8")
    return None


def run_testsuite_oracle(model_path: Path, test_suite_path: Path) -> Tuple[str, Optional[str]]:
    """Run Rq3ParallelTestSuiteOracle (merged model + test suite)."""
    err = _ensure_java_build()
    if err:
        return ("UNKNOWN", err)

    m = str(model_path.resolve())
    t = str(test_suite_path.resolve())
    cmd = (
        'java -cp "target/classes:target/lib/*:lib/alloy.jar" '
        f'Rq3ParallelTestSuiteOracle "{m}" "{t}"'
    )
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        timeout=300,
        capture_output=True,
        text=True,
        shell=True,
    )
    out = (r.stdout or "").strip()
    err_s = (r.stderr or "").strip()
    if r.returncode != 0 and not out:
        return ("UNKNOWN", err_s or out or None)
    lines = [s.rstrip("\n") for s in out.splitlines() if s.strip()]
    if not lines:
        return ("UNKNOWN", err_s or out or None)
    code_type = lines[0].strip().upper()
    if "SYNTAX_ERROR" in code_type:
        code_type = "SYNTAX_ERROR"
    err_msg = "\n".join(lines[1:]) if len(lines) > 1 else None
    return (code_type, err_msg)


def run_check_one(model_path: Path) -> Tuple[str, Optional[str]]:
    """Run the historical RQ3 primary classifier: Example --check-one."""
    err = _ensure_java_build()
    if err:
        return ("UNKNOWN", err)

    m = str(model_path.resolve())
    cmd = (
        'java -cp "target/classes:target/lib/*:lib/alloy.jar" '
        f'Example --check-one "{m}"'
    )
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        timeout=300,
        capture_output=True,
        text=True,
        shell=True,
    )
    out = (r.stdout or "").strip()
    err_s = (r.stderr or "").strip()
    if r.returncode != 0 and not out:
        return ("UNKNOWN", err_s or out or None)
    lines = [s.rstrip("\n") for s in out.splitlines() if s.strip()]
    if not lines:
        return ("UNKNOWN", err_s or out or None)
    code_type = lines[0].strip().upper()
    if "SYNTAX_ERROR" in code_type:
        code_type = "SYNTAX_ERROR"
    err_msg = "\n".join(lines[1:]) if len(lines) > 1 else None
    return (code_type, err_msg)


def code_type_to_result(ct: str) -> str:
    """Map Java CodeType to Cor / Syn / Sem / Unknown."""
    if ct in ("CORRECT_CODE", "SAME_CODE"):
        return "Cor"
    if ct == "SYNTAX_ERROR":
        return "Syn"
    if ct == "DIFF_OUTPUT":
        return "Sem"
    return "Unknown"


@dataclass
class CaseInfo:
    unique_id: str
    model_name: str
    predicate_name: str
    model_path: Path
    test_suite_path: Optional[Path]
    kind: str  # "original" or "llm"


def run_faulty_pred_equiv(case: CaseInfo) -> Tuple[str, Optional[str]]:
    """
    Bounded pred-vs-pred: gold predicate in ARepair/experiments/models/<model>.als vs faulty body
    in case.model_path (``Example --faulty-pred-equiv``). Scope: -Darepair.equiv.scope (default 5).
    """
    base = REPO_ROOT / "ARepair" / "experiments" / "models" / f"{case.model_name}.als"
    if not base.exists():
        return ("UNKNOWN", f"Base model not found: {base}")
    m = str(case.model_path.resolve())
    b = str(base.resolve())
    pred = case.predicate_name
    cmd = (
        'java -cp "target/classes:target/lib/*:lib/alloy.jar" '
        f'Example --faulty-pred-equiv "{b}" "{m}" "{pred}"'
    )
    r = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        timeout=300,
        capture_output=True,
        text=True,
        shell=True,
    )
    out = (r.stdout or "").strip()
    err_s = (r.stderr or "").strip()
    if r.returncode != 0 and not out:
        return ("UNKNOWN", err_s or out or None)
    lines = [s.rstrip("\n") for s in out.splitlines() if s.strip()]
    if not lines:
        return ("UNKNOWN", err_s or out or None)
    code_type = lines[0].strip().upper()
    if "SYNTAX_ERROR" in code_type:
        code_type = "SYNTAX_ERROR"
    err_msg = "\n".join(lines[1:]) if len(lines) > 1 else None
    return (code_type, err_msg)


def load_cases(info_root: Path) -> List[CaseInfo]:
    root = info_root
    orig_info = root / "repair_info_original.json"
    llm_info = root / "repair_info_llm.json"

    if not orig_info.exists() or not llm_info.exists():
        print("repair_info_original.json or repair_info_llm.json not found; aborting classification.")
        return []

    def _load(path: Path, kind: str) -> List[CaseInfo]:
        data = json.loads(path.read_text(encoding="utf-8"))
        cases: List[CaseInfo] = []
        for item in data:
            mid = item.get("model_path")
            if not mid:
                continue
            model_path = (REPO_ROOT / mid).resolve()
            ts = item.get("test_suite_path")
            test_suite_path = (REPO_ROOT / ts).resolve() if ts else None
            cases.append(
                CaseInfo(
                    unique_id=item.get("unique_id", ""),
                    model_name=item.get("model_name", ""),
                    predicate_name=item.get("predicate_name", ""),
                    model_path=model_path,
                    test_suite_path=test_suite_path,
                    kind=kind,
                )
            )
        return cases

    cases: List[CaseInfo] = []
    cases.extend(_load(orig_info, "original"))
    cases.extend(_load(llm_info, "llm"))
    return cases


def main() -> None:
    _load_env()
    ap = argparse.ArgumentParser(
        description=(
            "Classify faulty models: Example --check-one (primary) plus testsuite and "
            "pred-vs-pred equivalence diagnostics."
        )
    )
    ap.add_argument(
        "--info-root",
        default="",
        help=(
            "Directory containing repair_info_original.json and repair_info_llm.json "
            "(relative to repo root). If omitted, defaults to legacy "
            "result/Gemini/ARepair_FaultyRewrite."
        ),
    )
    args = ap.parse_args()

    if args.info_root:
        info_root = (REPO_ROOT / args.info_root).resolve()
    else:
        info_root = REPO_ROOT / "result" / "Gemini" / "ARepair_FaultyRewrite"

    cases = load_cases(info_root)
    if not cases:
        return

    print(f"=== Classify faulty models (original + LLM), total cases: {len(cases)} ===")
    print("mode: check-one primary + testsuite/predEquiv diagnostics; progress every 10 cases")

    results = []
    summary = {
        "validation": "check_one_primary_with_testsuite_and_pred_equiv_diagnostics",
        "total": 0,
        "Cor": 0,
        "Syn": 0,
        "Sem": 0,
        "Unknown": 0,
        "by_kind": {
            "original": {"Cor": 0, "Syn": 0, "Sem": 0, "Unknown": 0},
            "llm": {"Cor": 0, "Syn": 0, "Sem": 0, "Unknown": 0},
        },
        "checkOne_vs_testsuite_compared": 0,
        "checkOne_vs_testsuite_agree": 0,
        "checkOne_vs_predEquiv_compared": 0,
        "checkOne_vs_predEquiv_agree": 0,
    }

    agree_co_ts = 0
    compared_co_ts = 0
    agree_co_pe = 0
    compared_co_pe = 0

    for idx, case in enumerate(cases, start=1):
        print(f"[{idx}/{len(cases)}] {case.unique_id} ({case.kind})")
        if not case.model_path.exists():
            print(f"  -> SKIP: model file not found: {case.model_path}")
            result = {
                "unique_id": case.unique_id,
                "model_name": case.model_name,
                "predicate_name": case.predicate_name,
                "kind": case.kind,
                "model_path": str(case.model_path),
                "test_suite_path": str(case.test_suite_path) if case.test_suite_path else "",
                "code_type": "MISSING",
                "result": "Unknown",
                "error_message": f"Model file not found: {case.model_path}",
                "validation": "skipped",
            }
            results.append(result)
            continue

        ct, err_msg = run_check_one(case.model_path)
        r = code_type_to_result(ct)
        print(f"  -> check-one: code_type={ct}, result={r}")

        ts_ct = "UNKNOWN"
        ts_err: Optional[str] = None
        ts_r = "Unknown"
        if case.test_suite_path is not None and case.test_suite_path.exists():
            print(f"  -> testsuite: {case.test_suite_path.name}")
            ts_ct, ts_err = run_testsuite_oracle(case.model_path, case.test_suite_path)
            ts_r = code_type_to_result(ts_ct)
            print(f"  -> testsuite: code_type={ts_ct}, result={ts_r}")
        else:
            ts_err = f"missing or invalid test_suite_path: {case.test_suite_path}"
            print(f"  -> testsuite: SKIP ({ts_err})")

        pe_ct, pe_err = run_faulty_pred_equiv(case)
        pe_r = code_type_to_result(pe_ct)
        print(
            f"  -> predEquiv (gold<->faulty pred): code_type={pe_ct}, result={pe_r} "
            f"(bounded check P<=>P__cand)"
        )

        check_one_vs_testsuite_agree: Optional[bool] = None
        if ts_ct != "UNKNOWN":
            compared_co_ts += 1
            check_one_vs_testsuite_agree = r == ts_r
            if check_one_vs_testsuite_agree:
                agree_co_ts += 1
            summary["checkOne_vs_testsuite_compared"] = compared_co_ts
            summary["checkOne_vs_testsuite_agree"] = agree_co_ts

        check_one_vs_pred_equiv_agree: Optional[bool] = None
        if pe_ct != "UNKNOWN":
            compared_co_pe += 1
            check_one_vs_pred_equiv_agree = r == pe_r
            if check_one_vs_pred_equiv_agree:
                agree_co_pe += 1
            summary["checkOne_vs_predEquiv_compared"] = compared_co_pe
            summary["checkOne_vs_predEquiv_agree"] = agree_co_pe
        if idx % 10 == 0:
            print(
                "  -> [check-one diagnostics] cumulative agree: "
                f"testsuite={agree_co_ts}/{compared_co_ts}, "
                f"predEquiv={agree_co_pe}/{compared_co_pe}"
            )

        result = {
            "unique_id": case.unique_id,
            "model_name": case.model_name,
            "predicate_name": case.predicate_name,
            "kind": case.kind,
            "model_path": str(case.model_path),
            "test_suite_path": str(case.test_suite_path) if case.test_suite_path else "",
            "code_type": ct,
            "result": r,
            "error_message": err_msg,
            "validation": "check_one",
            "testsuite_oracle_code_type": ts_ct,
            "testsuite_oracle_result": ts_r,
            "testsuite_oracle_error_message": ts_err,
            "pred_equiv_code_type": pe_ct,
            "pred_equiv_result": pe_r,
            "pred_equiv_error_message": pe_err,
            "check_one_vs_testsuite_agree": check_one_vs_testsuite_agree,
            "check_one_vs_predEquiv_agree": check_one_vs_pred_equiv_agree,
        }
        summary["total"] += 1
        summary[r] += 1
        summary["by_kind"][case.kind][r] += 1

        results.append(result)

    out_path = info_root / "classification.json"
    out = {"results": results, "summary": summary}
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print("")
    print("=== Classification summary ===")
    print(json.dumps(summary, indent=2))
    print(f"Classification written to: {out_path}")


if __name__ == "__main__":
    main()
