#!/usr/bin/env python
"""
Evaluate ARepair NoTest responses using the existing Java pipeline.

Supports two modes:
  1. Legacy: Java constructs paths from -Darepair.result.subfolder=ARepairNoTest
  2. Direct: --result-dir <path> → -Darepair.result.dir=<path> (e.g. result/thesis/.../NoTest)

Env:
  AREPAIR_VALIDATION   testsuite (default) | equivalence
  AREPAIR_BENCH_MODELS comma-separated filter
"""

import argparse
import os
import subprocess
from pathlib import Path

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


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--result-dir", type=str, default=None,
                    help="Direct result dir (has responses/ and Alloy/ inside). "
                         "Passed to Java as -Darepair.result.dir.")
    args = ap.parse_args()

    if args.result_dir:
        result_dir = args.result_dir
        responses = Path(result_dir) / "responses"
        alloy_out = Path(result_dir) / "Alloy"
    else:
        result_dir = None
        responses = BASE_DIR / "result/Gemini/ARepairNoTest/responses"
        alloy_out = BASE_DIR / "result/Gemini/ARepairNoTest/Alloy"

    if not responses.is_dir() or not any(responses.iterdir()):
        print("No responses found in", responses)
        return

    bench = os.environ.get("AREPAIR_BENCH_MODELS", "").strip()
    mvn_args = [
        "mvn", "-q", "clean", "compile", "exec:java",
        "-Dexec.mainClass=Example",
        "-Dexec.args=ARepairNoTest",
    ]
    if result_dir:
        mvn_args.append("-Darepair.result.dir=" + result_dir)
    if bench:
        mvn_args.append("-Darepair.bench.models=" + bench)
        print("Bench filter:", bench)
    val_args = _arepair_validation_mvn_args()
    mvn_args.extend(val_args)
    print("Running Java (NoTest), result.dir=", result_dir or "(legacy)", ", validation=", val_args)
    r = subprocess.run(mvn_args, cwd=BASE_DIR, timeout=900)
    if r.returncode != 0:
        print("Java failed (return code", r.returncode, ")")
        return
    print("Done. NoTest evaluation written to", alloy_out)


if __name__ == "__main__":
    main()
