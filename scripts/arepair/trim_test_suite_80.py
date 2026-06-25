#!/usr/bin/env python
"""
Create 80% trimmed copies of the original ARepair test suites.

For each *.als in ARepair/experiments/test-suite, we keep the first 80% of
predicate/run blocks (pred ... / run ...), preserving order, and write the
result to ARepair/experiments/test-suite-80/<file>.als.

Usage:
  python scripts/arepair/trim_test_suite_80.py
"""

import math
from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



PROJECT_DIR = _artifact_repo_root()
SRC_DIR = PROJECT_DIR / "ARepair" / "experiments" / "test-suite"
DST_DIR = PROJECT_DIR / "ARepair" / "experiments" / "test-suite-80"


def split_blocks(lines: list[str]) -> tuple[list[str], list[list[str]]]:
    """
    Split into (header, blocks). A block starts with a line beginning with
    'pred ' and ends after the corresponding 'run ' line (the next line
    that starts with 'run ' is taken as the block terminator).
    """
    header: list[str] = []
    blocks: list[list[str]] = []

    idx = 0
    n = len(lines)

    # collect header until first 'pred ' line
    while idx < n and not lines[idx].lstrip().startswith("pred "):
        header.append(lines[idx])
        idx += 1

    while idx < n:
        # start of a block
        if not lines[idx].lstrip().startswith("pred "):
            idx += 1
            continue
        block: list[str] = []
        # collect pred ... until run line is included
        while idx < n:
            block.append(lines[idx])
            if lines[idx].lstrip().startswith("run "):
                idx += 1
                break
            idx += 1
        blocks.append(block)

    return header, blocks


def trim_file(src_path: Path, dst_path: Path, keep_ratio: float = 0.8) -> None:
    lines = src_path.read_text(encoding="utf-8", errors="ignore").splitlines()
    header, blocks = split_blocks(lines)

    if not blocks:
        # nothing to trim; copy header (or whole file if no header)
        dst_path.write_text("\n".join(lines), encoding="utf-8")
        return

    keep_n = max(1, math.ceil(len(blocks) * keep_ratio))
    kept_blocks = blocks[:keep_n]

    out_lines: list[str] = []
    out_lines.extend(header)
    if header and header[-1].strip():
        out_lines.append("")  # blank line between header and blocks

    for i, blk in enumerate(kept_blocks):
        out_lines.extend(blk)
        if i != len(kept_blocks) - 1:
            out_lines.append("")  # blank line between blocks

    dst_path.write_text("\n".join(out_lines), encoding="utf-8")


def main():
    DST_DIR.mkdir(parents=True, exist_ok=True)
    for src_path in sorted(SRC_DIR.glob("*.als")):
        dst_path = DST_DIR / src_path.name
        trim_file(src_path, dst_path)
        print(f"Trimmed {src_path.name} -> {dst_path.name}")


if __name__ == "__main__":
    main()
