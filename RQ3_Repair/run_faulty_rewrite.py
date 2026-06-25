#!/usr/bin/env python
"""
Experiment 4: Alloy-to-Alloy for faulty models using LLM.

This script:
- Reads prompt files under query/Gemini/ARepair_FaultyRewrite/<model>_<Pred>.txt
- Calls a Gemini model to generate 10 rewrites of the body of the target predicate (keeping it faulty)
- Saves raw LLM responses under result/Gemini/ARepair_FaultyRewrite/responses/<model>_<Pred>_k.txt
- Splices each rewritten predicate back into a single-faulty Alloy model and writes:
    ARepair/experiments/models/llm_faulty_models/<model>_<Pred>_llm_k.als
- Generates simple repair_info.json files for running ARepair on:
    - original faulty models (original_faulty_models)
    - LLM-rewritten faulty models (llm_faulty_models)

Usage (from project root):
  python scripts/faulty/run_faulty_rewrite.py --model gemini-3.1-pro-preview

Requires:
  - pip install google-genai
  - GOOGLE_API_KEY or GEMINI_API_KEY in env, or .env at project root
"""

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import List

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()


def _load_env() -> None:
    """Load .env from project root if present (KEY=VALUE per line, no quotes)."""
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


def get_genai_client(api_key: str):
    """Create and return a genai Client. Caller must close it when done."""
    try:
        from google.genai import Client
    except ImportError:
        raise RuntimeError("Install google-genai: pip install google-genai")
    return Client(api_key=api_key)


def call_gemini(prompt: str, model: str, client) -> str:
    """Call Gemini with a plain text prompt."""
    r = client.models.generate_content(model=model, contents=prompt)
    if not r or not getattr(r, "text", None):
        return ""
    return r.text.strip()


def _pred_pattern(pred_name: str):
    """Regex pattern that matches an Alloy predicate definition by name."""
    import re

    return re.compile(
        r"pred\s+"
        + re.escape(pred_name)
        + r"\s*(?:\[[^\]]*\]|\([^)]*\))?\s*\{",
        re.MULTILINE,
    )


def _find_matching_brace(s: str, open_brace_idx: int) -> int:
    """Return index of matching '}' for the '{' at open_brace_idx, or -1 if not found."""
    depth = 0
    for i in range(open_brace_idx, len(s)):
        c = s[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i
    return -1


def find_pred_span(module_text: str, pred_name: str) -> tuple[int, int]:
    """
    Find the [start, end) span of the full predicate definition for pred_name,
    including nested braces inside the body.
    Returns (-1, -1) if not found.
    """
    pat = _pred_pattern(pred_name)
    m = pat.search(module_text)
    if not m:
        return (-1, -1)
    start = m.start()
    open_idx = m.end() - 1
    close_idx = _find_matching_brace(module_text, open_idx)
    if close_idx < 0:
        return (-1, -1)
    return (start, close_idx + 1)


def replace_pred_definition(module_text: str, pred_name: str, new_pred_def: str) -> str:
    """Replace the definition of pred `pred_name` in `module_text` with `new_pred_def`."""
    a, b = find_pred_span(module_text, pred_name)
    if a < 0:
        # Fallback: return the new predicate alone so the caller can debug.
        return new_pred_def
    return module_text[:a] + new_pred_def.strip() + module_text[b:]


@dataclass
class FaultyCase:
    model_name: str          # e.g. "balancedBST"
    predicate_name: str      # e.g. "Balanced"
    prompt_path: Path        # prompt to send to Gemini
    faulty_model_path: Path  # base faulty model to splice into (single-fault version)

    @property
    def unique_id(self) -> str:
        return f"{self.model_name}_{self.predicate_name}"


def discover_faulty_cases() -> List[FaultyCase]:
    """
    Discover all faulty cases automatically from prompt + model naming:

    - Prompt files live under:
        query/Gemini/ARepair_FaultyRewrite/<model>/<Pred>.txt
      (we also support flat: .../model_Pred.txt if ever needed)
    - Single-fault models live under:
        ARepair/experiments/models/original_faulty_models/<model>_<Pred>.als

    Any (model, Pred) pair that has both a prompt and a faulty model
    will be included as a case.
    """
    qbase = BASE_DIR / "query" / "Gemini" / "ARepair_FaultyRewrite"
    mbase_original = (
        BASE_DIR / "ARepair" / "experiments" / "models" / "original_faulty_models"
    )

    cases: List[FaultyCase] = []

    if not qbase.exists():
        print(f"No prompt directory: {qbase}")
        return cases

    # Support both subdirectory style (model/pred.txt) and flat style (model_pred.txt).
    prompt_files = list(qbase.rglob("*.txt"))
    for p in prompt_files:
        # Skip files directly under qbase that are not of the form model_pred.txt
        rel = p.relative_to(qbase)
        if rel.parent == Path("."):
            # Flat: expect name like model_pred.txt
            if "_" not in p.stem:
                continue
            model_name, predicate_name = p.stem.split("_", 1)
        else:
            # Nested: qbase/model/Pred.txt
            model_name = rel.parent.name
            predicate_name = p.stem

        faulty_model = mbase_original / f"{model_name}_{predicate_name}.als"
        if not faulty_model.exists():
            print(
                f"[discover] Skip {model_name}-{predicate_name}: "
                f"no faulty model {faulty_model}"
            )
            continue

        cases.append(
            FaultyCase(
                model_name=model_name,
                predicate_name=predicate_name,
                prompt_path=p,
                faulty_model_path=faulty_model,
            )
        )

    # Sort for stable ordering
    cases.sort(key=lambda c: (c.model_name, c.predicate_name))

    # Exclude cases whose originals we decided to drop from the experiment
    # (their originals classify as Cor under Example --check-one).
    excluded_ids = {"arr_NoConflict", "bempl_CanEnter"}
    filtered = [c for c in cases if c.unique_id not in excluded_ids]
    print(
        f"Discovered {len(filtered)} faulty case(s) from prompts under {qbase} "
        f"and models under {mbase_original}"
    )
    return filtered


def run_faulty_rewrite(
    cases: List[FaultyCase],
    model: str,
    out_root: Path,
    dry_run: bool = False,
    limit: int = 0,
) -> None:
    """Call Gemini for each faulty case, save responses, and build rewritten models."""
    _load_env()
    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not dry_run and not api_key:
        raise SystemExit(
            "Set GOOGLE_API_KEY or GEMINI_API_KEY in env (or .env) for LLM calls."
        )

    # Where to store outputs (model-scoped so multi-model reruns don't overwrite):
    #   result/Gemini/RQ3_Repair/FaultyRewrite/<gemini-model>/
    #     responses/
    #     models/llm_faulty_models/
    #     repair_info_original.json
    #     repair_info_llm.json
    result_root = out_root
    responses_dir = result_root / "responses"
    llm_models_root = result_root / "models" / "llm_faulty_models"
    responses_dir.mkdir(parents=True, exist_ok=True)
    llm_models_root.mkdir(parents=True, exist_ok=True)

    # For ARepair later: simple repair_info.json for original vs rewritten
    repair_info_original = []
    repair_info_rewritten = []

    # Filter cases whose prompt/model exist
    active_cases: List[FaultyCase] = []
    for c in cases:
        if not c.prompt_path.exists():
            print(f"[skip] No prompt file: {c.prompt_path}")
            continue
        if not c.faulty_model_path.exists():
            print(f"[skip] No faulty model file: {c.faulty_model_path}")
            continue
        active_cases.append(c)

    if limit > 0:
        active_cases = active_cases[:limit]

    client = get_genai_client(api_key) if (not dry_run and active_cases) else None

    for idx, case in enumerate(active_cases, start=1):
        print(
            f"=== Case {idx}/{len(active_cases)}: "
            f"{case.model_name}-{case.predicate_name} ==="
        )
        prompt_text = case.prompt_path.read_text(encoding="utf-8")

        # Prepare entry for original faulty model once per case.
        # Store model_path as a path relative to project root so that it works
        # both on the host and inside the Docker container (where PROJECT_DIR
        # is /workspace).
        test_suite_rel = f"ARepair/experiments/test-suite/{case.model_name}.als"
        try:
            rel_original_model = case.faulty_model_path.relative_to(BASE_DIR)
        except ValueError:
            # Fallback: just use the original path string
            rel_original_model = case.faulty_model_path
        repair_info_original.append(
            {
                "unique_id": f"{case.unique_id}_original",
                "model_name": case.model_name,
                "predicate_name": case.predicate_name,
                "model_path": str(rel_original_model),
                "test_suite_path": test_suite_rel,
            }
        )

        # One raw response per predicate: we ask the model to produce 10
        # predicate definitions in a single answer.
        raw_response_path = responses_dir / f"{case.unique_id}.txt"

        if dry_run:
            print(
                f"[dry-run] Would call model={model} with prompt from {case.prompt_path} "
                "to generate 10 rewrites."
            )
            continue

        if raw_response_path.exists():
            response_text = raw_response_path.read_text(encoding="utf-8")
            print(f"[LLM] Using existing raw response: {raw_response_path}")
        else:
            print(f"[LLM] {case.model_name}-{case.predicate_name}: generate 10 rewrites in one call")
            response_text = call_gemini(prompt_text, model=model, client=client)
            raw_response_path.write_text(response_text, encoding="utf-8")
            print(f"[LLM] Raw response saved to {raw_response_path}")

        # Extract up to 10 predicate definitions from the raw response.
        pred_pat = _pred_pattern(case.predicate_name)
        matches: List[str] = []
        for m in pred_pat.finditer(response_text):
            start = m.start()
            open_idx = m.end() - 1
            close_idx = _find_matching_brace(response_text, open_idx)
            if close_idx < 0:
                continue
            matches.append(response_text[start : close_idx + 1].strip())

        if not matches:
            print(
                f"[warn] No full predicate definition for '{case.predicate_name}' "
                f"found in response for {case.unique_id}; skipping splicing (will not write models)."
            )
            matches = []
        if 0 < len(matches) < 10:
            print(
                f"[warn] Only found {len(matches)} predicate definition(s) for "
                f"{case.unique_id}; expected 10. Using all available."
            )

        faulty_text = case.faulty_model_path.read_text(encoding="utf-8")

        # For each extracted definition, write a snippet file and a full model,
        # and add an entry to repair_info_llm.
        for k, pred_def in enumerate(matches[:10], start=1):
            suffix = f"_{k}"
            snippet_path = responses_dir / f"{case.unique_id}{suffix}.txt"
            out_model_path = (
                llm_models_root
                / f"{case.model_name}_{case.predicate_name}_llm{suffix}.als"
            )

            if not snippet_path.exists():
                snippet_path.write_text(pred_def, encoding="utf-8")

            if out_model_path.exists():
                print(
                    f"[skip] {case.unique_id}{suffix}: llm_faulty_model already exists, "
                    "skipping rewrite."
                )
            else:
                rewritten_module = replace_pred_definition(
                    faulty_text, case.predicate_name, pred_def
                )
                out_model_path.write_text(rewritten_module, encoding="utf-8")
                print(f"[LLM] Rewritten faulty model -> {out_model_path}")

            # Prepare entry for this LLM-rewritten model
            try:
                rel_llm_model = out_model_path.relative_to(BASE_DIR)
            except ValueError:
                rel_llm_model = out_model_path
            repair_info_rewritten.append(
                {
                    "unique_id": f"{case.unique_id}_llm{suffix}",
                    "model_name": case.model_name,
                    "predicate_name": case.predicate_name,
                    "model_path": str(rel_llm_model),
                    "test_suite_path": test_suite_rel,
                }
            )

    if client is not None:
        client.close()

    # Write repair_info JSONs for later ARepair runs
    info_root = result_root
    if repair_info_original:
        orig_json = info_root / "repair_info_original.json"
        orig_json.write_text(
            json.dumps(repair_info_original, indent=2), encoding="utf-8"
        )
        print(f"[ARepair] Original repair_info -> {orig_json}")
    if repair_info_rewritten:
        llm_json = info_root / "repair_info_llm.json"
        llm_json.write_text(
            json.dumps(repair_info_rewritten, indent=2), encoding="utf-8"
        )
        print(f"[ARepair] LLM repair_info -> {llm_json}")
    elif repair_info_original:
        # e.g. --dry-run or --skip-llm: classify_faulty_models.py still needs both files
        llm_json = info_root / "repair_info_llm.json"
        llm_json.write_text("[]\n", encoding="utf-8")
        print(f"[ARepair] Empty LLM repair_info (no rewrites yet) -> {llm_json}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Run LLM-based predicate rewrite for faulty Alloy models."
    )
    ap.add_argument(
        "--model",
        default="gemini-3.1-pro-preview",
        help="Gemini model name (e.g., gemini-3.1-pro-preview, gemini-2.5-flash)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show which cases would be processed; do not call LLM.",
    )
    ap.add_argument(
        "--out-root",
        default="",
        help=(
            "Output root directory (relative to repo root). "
            "Default: result/Gemini/RQ3_Repair/FaultyRewrite/<model>"
        ),
    )
    ap.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Only process first N faulty cases (0 = all).",
    )
    args = ap.parse_args()

    cases = discover_faulty_cases()
    if not cases:
        print("No faulty cases configured.")
        return

    if args.out_root:
        out_root = (BASE_DIR / args.out_root).resolve()
    else:
        out_root = (
            BASE_DIR
            / "result"
            / "Gemini"
            / "RQ3_Repair"
            / "FaultyRewrite"
            / args.model
        )
    run_faulty_rewrite(
        cases,
        model=args.model,
        out_root=out_root,
        dry_run=args.dry_run,
        limit=args.limit,
    )


if __name__ == "__main__":
    main()

