#!/usr/bin/env python3
"""
Rebuild repair_info_llm.json by scanning models/llm_faulty_models/*.als and joining
with repair_info_original.json for test_suite_path and names.

Use when .als files exist but repair_info_llm.json was overwritten (e.g. dry-run wrote []).
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()
LLM_NAME_RE = re.compile(r"^(.+)_llm_(\d+)\.als$")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--info-root",
        required=True,
        help="RQ2 output dir (contains repair_info_original.json and models/llm_faulty_models/), relative to repo root or absolute",
    )
    args = ap.parse_args()
    info_root = Path(args.info_root)
    if not info_root.is_absolute():
        info_root = (BASE_DIR / info_root).resolve()

    orig_path = info_root / "repair_info_original.json"
    llm_dir = info_root / "models" / "llm_faulty_models"
    if not orig_path.exists():
        raise SystemExit(f"missing {orig_path}")
    if not llm_dir.is_dir():
        raise SystemExit(f"missing llm dir {llm_dir}")

    originals = json.loads(orig_path.read_text(encoding="utf-8"))
    key_to_meta: dict[str, dict] = {}
    for item in originals:
        mn = item.get("model_name", "")
        pn = item.get("predicate_name", "")
        k = f"{mn}_{pn}"
        key_to_meta[k] = {
            "model_name": mn,
            "predicate_name": pn,
            "test_suite_path": item.get("test_suite_path", ""),
        }

    out: list[dict] = []
    for als in sorted(llm_dir.glob("*.als")):
        m = LLM_NAME_RE.match(als.name)
        if not m:
            print(f"[skip] unexpected filename: {als.name}")
            continue
        stem, k_str = m.group(1), m.group(2)
        meta = key_to_meta.get(stem)
        if not meta:
            print(f"[skip] no original entry for stem {stem} ({als.name})")
            continue
        rel_model = als.relative_to(BASE_DIR)
        uid = f"{stem}_llm_{k_str}"
        out.append(
            {
                "unique_id": uid,
                "model_name": meta["model_name"],
                "predicate_name": meta["predicate_name"],
                "model_path": str(rel_model).replace("\\", "/"),
                "test_suite_path": meta["test_suite_path"],
            }
        )

    out.sort(key=lambda x: (x["model_name"], x["predicate_name"], int(x["unique_id"].rsplit("_llm_", 1)[-1])))
    out_path = info_root / "repair_info_llm.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(out)} entries -> {out_path}")


if __name__ == "__main__":
    main()
