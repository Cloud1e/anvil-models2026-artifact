#!/usr/bin/env python
"""
Evaluate Alloy-to-Alloy responses (WithTest and NoTest) using the existing Java pipeline.

Supports two modes:
  1. Legacy: Java constructs paths from -Darepair.result.subfolder (result/Gemini/ARepair_Alloy2Alloy_*)
  2. Direct: --result-dir-with / --result-dir-no → -Darepair.result.dir (thesis paths)

Env:
  AREPAIR_VALIDATION   testsuite (default) | equivalence
  AREPAIR_BENCH_MODELS comma-separated filter
"""

import argparse
import os
import subprocess
from pathlib import Path
from typing import Optional

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()


def _arepair_validation_mvn_args():
    v = os.environ.get("AREPAIR_VALIDATION", "testsuite").strip().lower()
    if v in ("equivalence", "equiv"):
        return ["-Darepair.validation=equivalence"]
    return ["-Darepair.validation=testsuite"]


def run_java_eval(subfolder: str, result_dir: Optional[str] = None) -> bool:
    bench = os.environ.get("AREPAIR_BENCH_MODELS", "").strip()
    mvn_args = [
        "mvn", "-q", "clean", "compile", "exec:java",
        "-Dexec.mainClass=Example",
        "-Dexec.args=" + subfolder,
    ]
    if result_dir:
        mvn_args.append("-Darepair.result.dir=" + result_dir)
    if bench:
        mvn_args.append("-Darepair.bench.models=" + bench)
    mvn_args.extend(_arepair_validation_mvn_args())
    r = subprocess.run(mvn_args, cwd=BASE_DIR, timeout=900)
    return r.returncode == 0


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result-dir-with", type=str, default=None,
                    help="Direct WithTest result dir (has responses/ and Alloy/ inside).")
    ap.add_argument("--result-dir-no", type=str, default=None,
                    help="Direct NoTest result dir (has responses/ and Alloy/ inside).")
    args = ap.parse_args()

    bench = os.environ.get("AREPAIR_BENCH_MODELS", "").strip()
    if bench:
        print("Bench filter:", bench)
    print("Validation MAVEN args:", _arepair_validation_mvn_args())

    with_alloy = Path(args.result_dir_with) / "Alloy" if args.result_dir_with else BASE_DIR / "result/Gemini/ARepair_Alloy2Alloy_WithTest/Alloy"
    no_alloy = Path(args.result_dir_no) / "Alloy" if args.result_dir_no else BASE_DIR / "result/Gemini/ARepair_Alloy2Alloy_NoTest/Alloy"

    print("=== Evaluate Alloy-to-Alloy WithTest ===")
    ok_with = run_java_eval("ARepair_Alloy2Alloy_WithTest", args.result_dir_with)
    if ok_with:
        print("  ->", with_alloy)
    else:
        print("  Java failed (WithTest)")

    print("")
    print("=== Evaluate Alloy-to-Alloy NoTest ===")
    ok_no = run_java_eval("ARepair_Alloy2Alloy_NoTest", args.result_dir_no)
    if ok_no:
        print("  ->", no_alloy)
    else:
        print("  Java failed (NoTest)")


if __name__ == "__main__":
    main()
