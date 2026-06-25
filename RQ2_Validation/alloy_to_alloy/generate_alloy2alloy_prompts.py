#!/usr/bin/env python
"""
Generate Alloy-to-Alloy prompts (WithTest and NoTest): prompt contains the
*entire correct model* from ARepair/experiments/models/<model>.als (no placeholder
replacement), and the LLM is asked to produce 10 equivalent but syntactically
different solutions.

- Model content = full file from ARepair/experiments/models/<model>.als (human-written).
  To ensure upstream version: cd ARepair && git pull
- WithTest = correct model + test suite block (from English-to-Alloy WithTest prompt) + tail.
- NoTest  = correct model + tail only.
- First line and tail instructions are kept consistent with the original design.
"""

import re
from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()
MODELS_DIR = BASE_DIR / "ARepair/experiments/models"
AREPAIR_QUERY = BASE_DIR / "query/Gemini/ARepair"
OUT_WITHTEST = BASE_DIR / "query/Gemini/ARepair_Alloy2Alloy_WithTest"
OUT_NOTEST = BASE_DIR / "query/Gemini/ARepair_Alloy2Alloy_NoTest"

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


def get_correct_model_content(model_name: str) -> str | None:
    """Return the full content of ARepair/experiments/models/<model>.als, or None if missing."""
    path = MODELS_DIR / f"{model_name}.als"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="ignore").strip()


def extract_test_suite_block(with_test_prompt: str) -> str | None:
    """Extract the test suite block from English-to-Alloy WithTest prompt (from // Test suite through do not output it.)."""
    m = re.search(
        r"\n// Test suite \(use these tests to verify your solutions\):\n.*?"
        r"Each candidate must satisfy every run\.\.\.expect command in the provided test suite\. "
        r"If a candidate fails any test, do not output it\.\s*\n",
        with_test_prompt,
        re.DOTALL,
    )
    return m.group(0) if m else None


def main():
    OUT_WITHTEST.mkdir(parents=True, exist_ok=True)
    OUT_NOTEST.mkdir(parents=True, exist_ok=True)

    for model_name in MODEL_PREDICATES:
        model_content = get_correct_model_content(model_name)
        if not model_content:
            print(f"  Skip {model_name}: no model at {MODELS_DIR / f'{model_name}.als'}")
            continue

        preds = MODEL_PREDICATES[model_name]
        pred_list = ", ".join(preds)
        if len(preds) == 1:
            first_line = "Give me exactly 10 unique solutions to the problem of synthesizing the body of the following Alloy predicate (without markdown or comments or ```) that are equivalent to the given predicate but syntactically different.\n\n"
            tail = (
                "Return exactly 10 lines for the predicate " + pred_list + " only, each line containing one predicate body. "
                "Do not include RepOk, any fact, or any other predicate. "
                "No numbering, bullet points, explanations, or other text before/after these lines. "
                "Only return the predicate body (the expression inside the braces)."
            )
        else:
            first_line = "Give me exactly 10 unique solutions per predicate that are equivalent to the given predicate bodies but syntactically different. Only the following predicates should appear in your output: " + pred_list + ".\n\n"
            tail = (
                "Return exactly 10 lines per predicate (total = 10 × " + str(len(preds)) + " = " + str(10 * len(preds)) + " lines), "
                "only for: " + pred_list + ". "
                "Each line formatted as \"predicateName: body\". "
                "Do not include RepOk, any fact (e.g. Acyclic), or any predicate not in the list above. "
                "No numbering or commentary before/after the list. Do not include introductions, explanations, or any extra text outside these lines."
            )

        # NoTest: correct model + tail only
        no_test_content = first_line + model_content + "\n\n" + tail
        (OUT_NOTEST / model_name).write_text(no_test_content, encoding="utf-8")
        print(f"  {model_name} -> ARepair_Alloy2Alloy_NoTest/")

        # WithTest: correct model + test suite (from English-to-Alloy WithTest) + tail
        with_test_prompt_path = AREPAIR_QUERY / model_name
        if not with_test_prompt_path.exists():
            (OUT_WITHTEST / model_name).write_text(no_test_content, encoding="utf-8")
            print(f"  {model_name} -> ARepair_Alloy2Alloy_WithTest/ (no test suite found)")
            continue
        with_test_full = with_test_prompt_path.read_text(encoding="utf-8", errors="ignore")
        suite_block = extract_test_suite_block(with_test_full)
        if suite_block:
            with_test_content = first_line + model_content.rstrip() + "\n\n" + suite_block + tail
        else:
            with_test_content = no_test_content
        (OUT_WITHTEST / model_name).write_text(with_test_content, encoding="utf-8")
        print(f"  {model_name} -> ARepair_Alloy2Alloy_WithTest/")

    print("Done. Response dirs: result/Gemini/ARepair_Alloy2Alloy_WithTest/responses/ and .../ARepair_Alloy2Alloy_NoTest/responses/")


if __name__ == "__main__":
    main()
