#!/usr/bin/env python
"""
Regenerate faulty-rewrite prompts for all single-fault models.

This script:
- Reads the meta-prompt template from scripts/faulty/prompt_faulty_pred_repair.txt
- For every file ARepair/experiments/models/original_faulty_models/<model>_<Pred>.als
  it generates/overwrites:
    query/Gemini/ARepair_FaultyRewrite/<model>_<Pred>.txt

We intentionally overwrite existing prompts so that any change to the meta-prompt
is consistently applied to all (model, predicate) pairs.

Usage (from project root):
  python scripts/faulty/regenerate_faulty_prompts.py
"""

from __future__ import annotations

from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()

TEMPLATE_PATH = BASE_DIR / "scripts" / "faulty" / "prompt_faulty_pred_repair.txt"
ORIGINAL_FAULTY_DIR = (
    BASE_DIR / "ARepair" / "experiments" / "models" / "original_faulty_models"
)
PROMPT_DIR = BASE_DIR / "query" / "Gemini" / "ARepair_FaultyRewrite"


def main() -> None:
    if not TEMPLATE_PATH.exists():
        raise SystemExit(f"Template not found: {TEMPLATE_PATH}")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")

    if not ORIGINAL_FAULTY_DIR.exists():
        raise SystemExit(f"original_faulty_models dir not found: {ORIGINAL_FAULTY_DIR}")

    PROMPT_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    # We only care about single-fault models of the form model_pred.als
    for als in sorted(ORIGINAL_FAULTY_DIR.glob("*.als")):
        stem = als.stem  # e.g., balancedBST_Balanced
        if "_" not in stem:
            continue
        model_name, pred_name = stem.split("_", 1)

        model_text = als.read_text(encoding="utf-8").strip()
        prompt_text = (
            template.replace("<FAULTY_MODEL_ALLOY_CODE>", model_text)
            .replace("<PREDICATE_NAME>", pred_name)
            .rstrip()
            + "\n"
        )

        out_path = PROMPT_DIR / f"{model_name}_{pred_name}.txt"
        out_path.write_text(prompt_text, encoding="utf-8")
        count += 1
        print(f"[write] prompt -> {out_path}")

    print(f"Regenerated prompts for {count} single-fault model(s).")


if __name__ == "__main__":
    main()

