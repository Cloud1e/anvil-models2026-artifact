#!/usr/bin/env python
"""
Temporary helper: call Gemini (e.g. 3.1 Pro) once for an English-to-Alloy WITH-TEST prompt.

Usage (from project root):
  python scripts/with_vs_without_test/english_to_alloy/run_gemini_etoa_single.py \\
    --model YOUR_GEMINI_MODEL_NAME \\
    --input /path/to/prompt.txt \\
    [--output /path/to/response.txt]

You can:
  - Copy the original WITH-TEST prompt into a txt file and point --input to it.
  - Pass --model as the 3.1 Pro model name you use in other experiments.
  - The script prints the model response to stdout and writes it to --output
    (default: <input>_response.txt in the same directory).

API key: loaded from project root .env (GOOGLE_API_KEY / GEMINI_API_KEY) or from environment.
"""

import argparse
import os
import sys
from pathlib import Path

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()


def _load_env() -> None:
    """Load .env from project root if present (KEY=VALUE per line)."""
    env_file = BASE_DIR / ".env"
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


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Call Gemini (e.g. 3.1 Pro) once for an English-to-Alloy WITH-TEST prompt."
    )
    ap.add_argument(
        "--model",
        required=True,
        help="Gemini model name (e.g. the 3.1 Pro model you currently use in other experiments).",
    )
    ap.add_argument(
        "--input",
        required=True,
        help="Path to a txt file containing the full prompt to send to Gemini.",
    )
    ap.add_argument(
        "--output",
        help="Where to save the response txt. Default: <input>_response.txt in the same directory.",
    )
    args = ap.parse_args()

    _load_env()

    prompt_path = Path(args.input).expanduser().resolve()
    if not prompt_path.exists():
        print(f"Input prompt file not found: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    prompt_text = prompt_path.read_text(encoding="utf-8")

    out_path: Path
    if args.output:
        out_path = Path(args.output).expanduser().resolve()
    else:
        out_path = prompt_path.with_name(prompt_path.stem + "_response.txt")

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Set GOOGLE_API_KEY or GEMINI_API_KEY (or in .env).", file=sys.stderr)
        sys.exit(1)

    try:
        from google.genai import Client
    except ImportError:
        print("Install: pip install google-genai", file=sys.stderr)
        sys.exit(1)

    client = Client(api_key=api_key)
    try:
        resp = client.models.generate_content(model=args.model, contents=prompt_text)
    finally:
        client.close()

    text = getattr(resp, "text", None) or ""
    text = text.strip()

    # Print to stdout for直接查看 / 手动复制
    print(text)

    # Also save to file for对比 / 归档
    out_path.write_text(text, encoding="utf-8")
    print(f"\n[Saved response to: {out_path}]", file=sys.stderr)


if __name__ == "__main__":
    main()

