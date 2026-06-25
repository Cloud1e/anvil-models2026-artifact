#!/usr/bin/env python
"""
Generate single-fault Alloy models and corresponding LLM prompts
for all (model, predicate) pairs where we can find a faulty predicate
definition in ARepair/experiments/realbugs.

For each entry in MODEL_PREDICATES:
  - Base model:   ARepair/experiments/models/<model>.als
  - Realbugs:     ARepair/experiments/realbugs/<model>*.als
  - Faulty model: ARepair/experiments/models/original_faulty_models/<model>_<Pred>.als
  - Prompt:       query/Gemini/ARepair_FaultyRewrite/<model>_<Pred>.txt

Strategy:
  - For each <model>, read all realbugs/<model>*.als.
  - For each predicate name in MODEL_PREDICATES[model], find the first
    realbug file that contains a definition `pred <Pred> { ... }`.
  - Extract that faulty predicate definition and replace the corresponding
    predicate in the base model to build a single-fault model.
  - Use that single-fault model text to create a prompt file that asks
    Gemini to REWRITE ONLY the body of that predicate (keeping it faulty).

Existing files are left untouched by default (we skip them), so you can
re-run this script safely as you add more realbugs.

Usage (from project root):
  python scripts/faulty/generate_original_faulty_models_and_prompts.py
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()

MODELS_DIR = BASE_DIR / "ARepair" / "experiments" / "models"
REALBUGS_DIR = BASE_DIR / "ARepair" / "experiments" / "realbugs"
ORIGINAL_FAULTY_DIR = MODELS_DIR / "original_faulty_models"
PROMPT_DIR = BASE_DIR / "query" / "Gemini" / "ARepair_FaultyRewrite"


# Copied/adapted from scripts/arepair/run_arepair.py
MODEL_PREDICATES: Dict[str, List[str]] = {
    "arr": ["NoConflict"],
    "balancedBST": ["Balanced", "HasAtMostOneChild", "Sorted"],
    "bempl": ["CanEnter"],
    # For cd, we only include predicates that have an explicit faulty body
    # in the realbugs benchmark. ClassHierarchy is a composite over these
    # predicates and does not have its own faulty definition, so we exclude it
    # from the faulty-formula rewriting experiment.
    "cd": ["Acyclic", "AllExtObject", "ObjectNoExt"],
    "dll": ["ConsistentPreAndNxt", "Sorted", "UniqueElem"],
    # For farmer, only crossRiver has an explicit faulty body in farmerFaulty.als.
    # solvePuzzle itself is not directly modified, so we exclude it.
    "farmer": ["crossRiver"],
    "grade": ["PolicyAllowsGrading"],
    "other": ["CanEnter"],
    "student": ["Contains", "Count", "Loop", "Sorted"],
}


def _pred_pattern(pred_name: str) -> re.Pattern:
    """Regex pattern that matches an Alloy predicate definition by name."""
    return re.compile(
        r"pred\s+"
        + re.escape(pred_name)
        + r"\s*(?:\[[^\]]*\]|\([^)]*\))?\s*\{[\s\S]*?\}",
        re.MULTILINE,
    )


def find_pred_definition(module_text: str, pred_name: str) -> Optional[str]:
    pat = _pred_pattern(pred_name)
    m = pat.search(module_text)
    return m.group(0) if m else None


def replace_pred_definition(
    module_text: str, pred_name: str, new_pred_def: str
) -> str:
    """Replace the definition of pred `pred_name` in `module_text` with `new_pred_def`."""
    pat = _pred_pattern(pred_name)
    if not pat.search(module_text):
        return module_text
    return pat.sub(new_pred_def, module_text, count=1)


def build_faulty_model(model_name: str, pred_name: str) -> Optional[str]:
    """Return text of single-fault model for (model_name, pred_name), or None."""
    base_path = MODELS_DIR / f"{model_name}.als"
    if not base_path.exists():
        print(f"[skip] base model not found: {base_path}")
        return None
    base_text = base_path.read_text(encoding="utf-8")

    # Search realbugs/<model>*.als for a faulty definition of this predicate.
    candidates = sorted(REALBUGS_DIR.glob(f"{model_name}*.als"))
    faulty_def: Optional[str] = None
    faulty_source: Optional[Path] = None
    for rb in candidates:
        txt = rb.read_text(encoding="utf-8")
        m = find_pred_definition(txt, pred_name)
        if m:
            faulty_def = m
            faulty_source = rb
            break

    if not faulty_def:
        print(
            f"[skip] no faulty predicate '{pred_name}' found in "
            f"realbugs/{model_name}*.als"
        )
        return None

    print(
        f"[use] {model_name}.{pred_name} faulty definition from {faulty_source.name}"
    )
    return replace_pred_definition(base_text, pred_name, faulty_def)


PROMPT_TEMPLATE = """Task:
Rewrite the body of a faulty Alloy predicate into a different syntactic form.
Keep the predicate name and parameters exactly the same.
Do not fix any potential bug in the predicate. The rewritten predicate should preserve the current behavior.

Faulty model:
{model_text}

Target predicate name:
{pred_name}

Requirements:
- Do not change the predicate name.
- Do not change the parameter list.
- Keep the current (possibly faulty) behavior; do NOT correct the bug.
- Only rewrite the body of the target predicate into a different Alloy expression.
- Do not introduce new predicates, functions, signatures, or comments.

Output:
Return ONLY the rewritten predicate definition as Alloy code (including its header and body).
Do not add any explanation or extra text.
"""


def main() -> None:
    ORIGINAL_FAULTY_DIR.mkdir(parents=True, exist_ok=True)
    PROMPT_DIR.mkdir(parents=True, exist_ok=True)

    for model_name, preds in MODEL_PREDICATES.items():
        for pred_name in preds:
            out_model_path = ORIGINAL_FAULTY_DIR / f"{model_name}_{pred_name}.als"
            prompt_path = PROMPT_DIR / f"{model_name}_{pred_name}.txt"

            if out_model_path.exists() and prompt_path.exists():
                print(
                    f"[skip] {model_name}_{pred_name}: faulty model and prompt already exist"
                )
                continue

            faulty_model_text = build_faulty_model(model_name, pred_name)
            if not faulty_model_text:
                continue

            # Write faulty model if not present
            if not out_model_path.exists():
                out_model_path.write_text(faulty_model_text, encoding="utf-8")
                print(f"[write] faulty model -> {out_model_path}")

            # Write prompt if not present
            if not prompt_path.exists():
                prompt_text = PROMPT_TEMPLATE.format(
                    model_text=faulty_model_text.strip(),
                    pred_name=pred_name,
                )
                prompt_path.write_text(prompt_text, encoding="utf-8")
                print(f"[write] prompt -> {prompt_path}")


if __name__ == "__main__":
    main()

