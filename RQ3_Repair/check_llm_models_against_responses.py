#!/usr/bin/env python
"""
Quick consistency check between LLM response snippets and llm_faulty_models.

For each snippet file:
  result/Gemini/ARepair_FaultyRewrite/responses/<model>_<Pred>_<k>.txt

we locate the corresponding rewritten model:
  ARepair/experiments/models/llm_faulty_models/<model>_<Pred>_llm_<k>.als

and verify that the predicate body from the snippet appears (up to whitespace)
inside the full Alloy module. This is only a sanity check that our manual
fixes did not accidentally drop or radically change the LLM output.
"""

from pathlib import Path
import re

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")




BASE_DIR = _artifact_repo_root()
RESP_DIR = BASE_DIR / "result" / "Gemini" / "ARepair_FaultyRewrite" / "responses"
LLM_DIR = (
    BASE_DIR
    / "ARepair"
    / "experiments"
    / "models"
    / "llm_faulty_models"
)


def extract_pred_body(text: str, pred_name: str) -> str:
    """
    Extract `pred <name> ... { ... }` block from a response text.

    If no such block is found, fall back to the full text (after stripping),
    so that we still check something rather than silently skipping.
    """
    pat = re.compile(
        r"pred\s+"
        + re.escape(pred_name)
        + r"\s*(?:\[[^\]]*\]|\([^)]*\))?\s*\{[\s\S]*?\}",
        re.MULTILINE,
    )
    m = pat.search(text)
    if not m:
        return text.strip()

    code = m.group(0)
    lines = [ln.rstrip() for ln in code.splitlines()]

    # Drop leading/trailing empty lines.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def normalize_for_compare(s: str) -> str:
    """
    Normalize Alloy code for robust substring comparison:
    - strip each line
    - drop completely empty lines
    - collapse all whitespace (spaces, newlines, tabs) to single spaces
    """
    lines = [ln.strip() for ln in s.splitlines() if ln.strip()]
    joined = " ".join(lines)
    return re.sub(r"\s+", " ", joined)


def main() -> None:
    if not RESP_DIR.exists():
        print(f"Responses directory not found: {RESP_DIR}")
        return

    total = 0
    ok = 0
    mismatches = []
    missing_models = []

    for resp_path in sorted(RESP_DIR.glob("*.txt")):
        stem = resp_path.stem  # e.g. balancedBST_Balanced_5 or balancedBST_Balanced
        parts = stem.split("_")

        # Only check numbered snippets: ..._<k>.txt
        if len(parts) < 3:
            continue

        model_name = parts[0]
        pred_name = parts[1]
        k = parts[2]

        llm_filename = f"{model_name}_{pred_name}_llm_{k}.als"
        llm_path = LLM_DIR / llm_filename

        total += 1

        if not llm_path.exists():
            print(f"[MISS] LLM model not found for {resp_path.name} -> {llm_filename}")
            missing_models.append((resp_path.name, llm_filename))
            continue

        resp_text = resp_path.read_text(encoding="utf-8")
        llm_text = llm_path.read_text(encoding="utf-8")

        resp_pred = extract_pred_body(resp_text, pred_name)

        # 更严格的检查：要求响应中的谓词块作为原样子串出现在
        # 模型中，并且末尾紧跟一个换行（避免 `} with "..."` 这类尾巴）。
        raw_block = resp_pred.rstrip() + "\n"

        if raw_block in llm_text:
            print(f"[OK]        {stem}  matched in  {llm_filename}")
            ok += 1
        else:
            print(f"[MISMATCH]  {stem}  NOT found in {llm_filename}")
            mismatches.append((resp_path.name, llm_filename))

    print("\n==== Summary ====")
    print(f"Total snippets checked: {total}")
    print(f"OK: {ok}")
    print(f"Missing models: {len(missing_models)}")
    print(f"Content mismatches: {len(mismatches)}")

    if missing_models:
        print("\nMissing model files:")
        for resp_name, llm_name in missing_models:
            print(f"  - {resp_name} -> {llm_name}")

    if mismatches:
        print("\nContent mismatches (snippet not found in model):")
        for resp_name, llm_name in mismatches:
            print(f"  - {resp_name} vs {llm_name}")


if __name__ == "__main__":
    main()

