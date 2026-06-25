#!/usr/bin/env python
"""
Generate ARepair "NoTest" prompts from existing "WithTest" prompts.

Reads query/<provider>/ARepair/<model> (with test suite in prompt), strips the
test suite and test-related instructions, writes query/<provider>/ARepairNoTest/<model>.

Does not require Example.java or ARepair/experiments/models; reuses existing prompt files.
"""

import re
from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()
PROVIDERS = ("Gemini",)  # extend to ("Gemini", "OpenAI", "DeepSeek") if needed
AREPAIR_QUERY = "query/{provider}/ARepair"
AREPAIR_NO_TEST_QUERY = "query/{provider}/ARepairNoTest"


def first_line_without_test_suite(line: str) -> str:
    """Change first line to drop 'and pass all tests in the test suite'."""
    if "pass all tests in the test suite" in line:
        line = line.replace(" that are correct with respect to the properties described in the comments and pass all tests in the test suite:", " that are correct with respect to the properties described in the comments.")
        line = line.replace(" and pass all tests in the test suite.", ".")
        line = line.replace(" and pass all tests in the test suite:", ".")
    return line


def strip_test_suite_from_prompt(content: str) -> str:
    """Remove test suite block and the 'Each candidate must satisfy...' line."""
    # Remove from "// Test suite (use these tests..." through "If a candidate fails any test, do not output it."
    pattern = re.compile(
        r"\n// Test suite \(use these tests to verify your solutions\):\n.*?"
        r"Each candidate must satisfy every run\.\.\.expect command in the provided test suite\. "
        r"If a candidate fails any test, do not output it\.\s*\n",
        re.DOTALL,
    )
    out = pattern.sub("\n", content)
    # Fix first line
    lines = out.split("\n")
    if lines:
        lines[0] = first_line_without_test_suite(lines[0])
        out = "\n".join(lines)
    return out


def main() -> None:
    for provider in PROVIDERS:
        src_dir = BASE_DIR / AREPAIR_QUERY.format(provider=provider)
        dst_dir = BASE_DIR / AREPAIR_NO_TEST_QUERY.format(provider=provider)
        if not src_dir.is_dir():
            print(f"Skip {provider}: not found {src_dir}")
            continue
        dst_dir.mkdir(parents=True, exist_ok=True)
        for f in sorted(src_dir.iterdir()):
            if f.name.startswith("."):
                continue
            if not f.is_file():
                continue
            content = f.read_text(encoding="utf-8", errors="ignore")
            if "// Test suite" not in content:
                print(f"  Skip {f.name} (no test suite block)")
                continue
            no_test = strip_test_suite_from_prompt(content)
            out_path = dst_dir / f.name
            out_path.write_text(no_test, encoding="utf-8")
            print(f"  {provider}: {f.name} -> {dst_dir.name}/{f.name}")


if __name__ == "__main__":
    main()
