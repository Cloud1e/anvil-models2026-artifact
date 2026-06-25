#!/usr/bin/env python
"""
LLM-based syntax error fix for Alloy-to-Alloy: use Alloy parser error message to fix Syn items.

Reads result/Gemini/<subfolder>/Alloy/SynItems/*.als and *.err (written by Java when status is Syn).
For each item: call Gemini with broken code + error message, get fixed code; re-validate with Java
--check-one. Up to 3 iterations. Saves all prompts and responses under .../SynFixLog/ for inspection
and manual testing.

Table headers: Syn (syntax error), Sem (semantic/wrong). Records: total to fix, fixed in 1/2/3 iters,
Fixed(<3) e.g. 3/5, still Syn, became Sem. Original SE -> New (Cor / Syn / Sem).

Usage:
  python fix_syntax_llm.py ARepair_Alloy2Alloy_WithTest [--model gemini-1.5-flash] [--dry-run] [--max-iter 3]
  python fix_syntax_llm.py ARepair_Alloy2Alloy_NoTest

Requires: pip install google-genai.
Key: set env GOOGLE_API_KEY or GEMINI_API_KEY; or put in project root .env (one line: GOOGLE_API_KEY=your_key).
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def _artifact_repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pom.xml").is_file() and (parent / "RQ1_Generation").is_dir() and (parent / "ARepair").is_dir():
            return parent
    raise RuntimeError("Could not locate artifact root")



BASE_DIR = _artifact_repo_root()
JAVA_PREPARED = False  # lazily run mvn package once, then use plain java for --check-one
MODELS_DIR = BASE_DIR / "ARepair" / "experiments" / "models"


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


def run_check_one(als_path: Path) -> Tuple[str, Optional[str]]:
    """Run Java --check-one on an .als file. Returns (code_type, error_message_or_none).

    For speed we avoid mvn exec:java per call: on first use we run mvn package once,
    then use java -cp "target/classes:target/lib/*:lib/..." Example --check-one <file>.
    """
    global JAVA_PREPARED
    if not JAVA_PREPARED:
        # One-time compile and copy deps; then use plain java for all --check-one calls
        prep = subprocess.run(
            ["mvn", "-q", "-DskipTests", "package"],
            cwd=BASE_DIR,
            timeout=600,
        )
        if prep.returncode != 0:
            return ("UNKNOWN", "mvn package failed (see Maven output)")
        JAVA_PREPARED = True

    path_str = str(als_path.resolve())
    # Direct java invocation; classpath: target/classes, target/lib/*, lib Alloy jar
    cmd = (
        'java -cp "target/classes:target/lib/*:lib/alloy.jar" '
        f'Example --check-one "{path_str}"'
    )
    r = subprocess.run(
        cmd,
        cwd=BASE_DIR,
        timeout=120,
        capture_output=True,
        text=True,
        shell=True,
    )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode != 0 and not out:
        return ("UNKNOWN", err or out or None)
    lines = [s.rstrip("\n") for s in out.splitlines() if s.strip()]
    if not lines:
        return ("UNKNOWN", err or out or None)
    code_type = lines[0].upper()
    if "SYNTAX_ERROR" in code_type:
        code_type = "SYNTAX_ERROR"
    # Join all remaining lines as a single multi-line parser error message,
    # so prompts can see the full Alloy error (e.g., expected tokens list).
    err_msg = "\n".join(lines[1:]) if len(lines) > 1 else None
    return (code_type, err_msg)


def code_type_to_result(ct: str) -> str:
    if ct in ("CORRECT_CODE", "SAME_CODE"):
        return "Cor"
    if ct == "SYNTAX_ERROR":
        return "Syn"
    if ct == "DIFF_OUTPUT":
        return "Sem"
    return "Unknown"


def extract_alloy_code(text: str) -> str:
    """Take first ```alloy ... ``` or full text if no block."""
    m = re.search(r"```(?:alloy)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return text.strip()


def _pred_pattern(pred_name: str) -> re.Pattern:
    """Return a regex pattern that matches an Alloy predicate definition.

    Supports:
      - pred name[...] {...}
      - pred name(...) {...}
      - pred name {...}
    """
    return re.compile(
        r"pred\s+"
        + re.escape(pred_name)
        + r"\s*(?:\[[^\]]*\]|\([^)]*\))?\s*\{[\s\S]*?\}",
        re.MULTILINE,
    )


def _split_pred_header_body(pred_text: str) -> Tuple[str, str, str]:
    """Split a predicate definition into (header_with_open_brace, body, closing_brace_and_suffix).

    Example shape:
      pred P(...) {
        ... body ...
      }

    We consider everything up to and including the first '{' as the "header",
    everything between the first '{' and the last '}' as the body, and from
    the last '}' to the end as the suffix.
    """
    start = pred_text.find("{")
    end = pred_text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        # Degenerate; treat whole text as body to avoid crashing.
        return ("", pred_text, "")
    header = pred_text[: start + 1]
    body = pred_text[start + 1 : end]
    suffix = pred_text[end:]
    return (header, body, suffix)


def replace_pred_definition(module_text: str, pred_name: str, new_pred_def: str) -> str:
    """Replace the definition of pred `pred_name` in `module_text` with `new_pred_def`.

    Expects new_pred_def to be a full Alloy predicate declaration, e.g.:
      pred Acyclic() { ... }
    If we cannot find a matching predicate header in the original text, we fall back to
    returning new_pred_def alone (the caller can decide how to handle that).
    """
    # Use a pattern that supports [], (), or no argument list.
    pattern = _pred_pattern(pred_name)
    if not pattern.search(module_text):
        return new_pred_def
    return pattern.sub(new_pred_def, module_text, count=1)


def build_context_module_from_models(syn_id: str, broken_module: str) -> str:
    """Build a smaller, test-free context module for syntax fix, using the
    original human-written model from ARepair/experiments/models and swapping in
    the broken predicate definition from the SynItems module.

    If anything goes wrong (cannot infer names, missing model file, predicate
    not found), this function raises an exception instead of silently falling
    back, so the caller can log and skip the item.
    """
    parts = syn_id.split("_")
    if len(parts) < 2:
        raise ValueError(f"cannot infer model/predicate from syn_id '{syn_id}'")
    model_name, pred_name = parts[0], parts[1]
    model_path = MODELS_DIR / f"{model_name}.als"
    if not model_path.exists():
        raise FileNotFoundError(f"no base model at {model_path}")
    base_model = model_path.read_text(encoding="utf-8")

    # Extract broken predicate definition from the SynItems module.
    broken_pat = _pred_pattern(pred_name)
    m_broken = broken_pat.search(broken_module)
    if not m_broken:
        raise ValueError(
            f"cannot find predicate '{pred_name}' definition in SynItems module for '{syn_id}'"
        )
    broken_pred_def = m_broken.group(0)

    # For robustness, replace the entire predicate definition in the base model
    # with the broken one from SynItems. This guarantees we do not accidentally
    # create mismatched braces or parentheses when the two bodies have
    # different internal block structures.
    return replace_pred_definition(base_model, pred_name, broken_pred_def)


def get_genai_client(api_key: str):
    """Create and return a genai Client. Caller must close it when done."""
    try:
        from google.genai import Client
    except ImportError:
        print("Install: pip install google-genai", file=sys.stderr)
        raise
    return Client(api_key=api_key)


def call_gemini(prompt: str, model: str, client) -> str:
    """Call model with prompt using an existing Client (reused across calls)."""
    r = client.models.generate_content(model=model, contents=prompt)
    if not r or not getattr(r, "text", None):
        return ""
    return r.text.strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Fix Alloy syntax errors with LLM (Gemini).")
    ap.add_argument("subfolder", help="e.g. ARepair_Alloy2Alloy_WithTest or ARepair_Alloy2Alloy_NoTest")
    ap.add_argument("--model", default="gemini-2.5-flash", help="Gemini model (2.0 deprecated for new users)")
    ap.add_argument("--dry-run", action="store_true", help="Only list Syn items, do not call API")
    ap.add_argument("--max-iter", type=int, default=3, help="Max fix iterations per item (default 3)")
    ap.add_argument("--limit", type=int, default=0, help="Only process first N Syn items (0 = all). Use e.g. 2 to test a few for free.")
    args = ap.parse_args()

    _load_env()

    subfolder = args.subfolder
    alloy_dir = BASE_DIR / "result" / "Gemini" / subfolder / "Alloy"
    syn_items_dir = alloy_dir / "SynItems"
    # Use a per-model subdirectory so different LLM models do not overwrite each other's fixes
    syn_fix_log_dir = BASE_DIR / "result" / "Gemini" / subfolder / "SynFixLog" / args.model.replace("/", "_")

    if not syn_items_dir.exists():
        print("No SynItems dir:", syn_items_dir)
        print("(No syntax errors in responses, or run evaluation first so Java can write Syn items.)")
        sys.exit(0)

    als_files = sorted(syn_items_dir.glob("*.als"))
    if not als_files:
        print("No .als files in", syn_items_dir)
        sys.exit(0)
    if args.limit > 0:
        als_files = als_files[: args.limit]
        print("Limit: processing only first", len(als_files), "Syn item(s).")

    api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not args.dry_run and not api_key:
        print("Set GOOGLE_API_KEY or GEMINI_API_KEY for LLM calls (see .env).", file=sys.stderr)
        sys.exit(1)

    # Reuse one client for all LLM calls (faster)
    client = get_genai_client(api_key) if (not args.dry_run and als_files) else None

    syn_fix_log_dir.mkdir(parents=True, exist_ok=True)
    system_prompt = (
        "You are fixing Alloy specification syntax errors. The user will provide the full Alloy module "
        "containing exactly one predicate that is currently broken, and the parser error message.\n\n"
        "Your task is to fix ONLY that predicate's definition so that the whole module parses without "
        "syntax errors. All other sigs, facts, predicates, and tests must remain unchanged.\n\n"
        "Reply with ONLY the complete fixed predicate definition (including the 'pred name(...) { ... }' "
        "header and body), no explanation and no other code. Do NOT return the rest of the module."
    )
    results: List[dict] = []
    # Load previous syn_fix_results.json (if any) so we can skip items already fixed as Cor/Sem
    existing_by_id: Dict[str, dict] = {}
    existing_json = syn_fix_log_dir / "syn_fix_results.json"
    if existing_json.exists():
        try:
            data = json.loads(existing_json.read_text(encoding="utf-8"))
            for r in data.get("results", []):
                rid = r.get("id")
                if rid:
                    existing_by_id[rid] = r
        except Exception:
            pass
    fixed_in_1 = fixed_in_2 = fixed_in_3 = still_syn = became_sem = 0

    total_items = len(als_files)
    print(
        f"=== Start Syn fix for subfolder={subfolder}, model={args.model}, "
        f"items={total_items}, max_iter={args.max_iter} ==="
    )

    for idx, als_path in enumerate(als_files, start=1):
        syn_id = als_path.stem
        # If this Syn was already resolved to Cor/Sem in a previous run, skip to avoid redundant LLM calls
        prev = existing_by_id.get(syn_id)
        if prev and prev.get("final") in {"Cor", "Sem"} and not args.dry_run:
            print(
                f"[{subfolder}] item {idx}/{total_items} ({syn_id}): "
                f"already fixed as {prev.get('final')} in previous run, skip."
            )
            results.append(prev)
            continue
        err_path = als_path.with_suffix(".err")
        err_msg = err_path.read_text(encoding="utf-8").strip() if err_path.exists() else ""
        broken = als_path.read_text(encoding="utf-8")

        if args.dry_run:
            print(
                f"[{subfolder}] item {idx}/{total_items} ({syn_id}) dry-run "
                f"-> err len: {len(err_msg)}"
            )
            results.append({"id": syn_id, "dry_run": True})
            continue

        log_dir = syn_fix_log_dir / syn_id
        log_dir.mkdir(parents=True, exist_ok=True)
        # Build a cleaner, test-free context module using the original
        # human-written model from ARepair/experiments/models and only swapping in
        # the broken predicate definition. If this fails, log details and skip.
        try:
            current_code = build_context_module_from_models(syn_id, broken)
        except Exception as e:
            print(
                f"[SynFix] skip {syn_id}: failed to build context from base model: {e}"
            )
            head = "\n".join(broken.splitlines()[:80])
            print(f"[SynFix] broken module head for {syn_id}:\n{head}\n")
            results.append({
                "id": syn_id,
                "final": "Syn",
                "fixed_at_iter": None,
                "model": args.model,
                "error": str(e),
            })
            continue
        current_err = err_msg
        final_result = "Syn"
        fixed_at_iter: int | None = None

        # Try to infer predicate name from syn_id, which typically looks like model_pred_k.
        pred_name = None
        parts = syn_id.split("_")
        if len(parts) >= 2:
            pred_name = parts[1]

        for it in range(1, args.max_iter + 1):
            print(
                f"[{subfolder}] item {idx}/{total_items} ({syn_id}), "
                f"iter {it}/{args.max_iter}: call LLM..."
            )
            if pred_name:
                user_prompt = (
                    f"The following Alloy module has a syntax error in the predicate `{pred_name}`.\n\n"
                    "Full module:\n\n"
                    + current_code
                    + "\n\nParser error:\n"
                    + (current_err or "(no message)")
                    + "\n\nOutput ONLY the complete fixed definition of that predicate, in Alloy syntax."
                )
            else:
                # Fallback: behave like old prompt (fix whole module) if we could not infer a predicate name.
                user_prompt = (
                    "Alloy code with syntax error:\n\n"
                    + current_code
                    + "\n\nParser error:\n"
                    + (current_err or "(no message)")
                    + "\n\nOutput only the fixed full Alloy code."
                )
            full_prompt = system_prompt + "\n\n" + user_prompt
            (log_dir / f"iter{it}_prompt.txt").write_text(full_prompt, encoding="utf-8")

            response = call_gemini(full_prompt, args.model, client)
            (log_dir / f"iter{it}_response.txt").write_text(response, encoding="utf-8")
            fixed_snippet = extract_alloy_code(response)
            if not fixed_snippet:
                fixed_snippet = response

            if pred_name:
                fixed_code = replace_pred_definition(current_code, pred_name, fixed_snippet)
            else:
                fixed_code = fixed_snippet

            fixed_path = log_dir / f"iter{it}_fixed.als"
            fixed_path.write_text(fixed_code, encoding="utf-8")

            print(
                f"[{subfolder}] item {idx}/{total_items} ({syn_id}), "
                f"iter {it}/{args.max_iter}: run Java --check-one..."
            )
            code_type, new_err = run_check_one(fixed_path)
            result = code_type_to_result(code_type)
            print(
                f"[{subfolder}] item {idx}/{total_items} ({syn_id}), "
                f"iter {it}/{args.max_iter}: check-one result={result} "
                f"(raw={code_type})"
            )
            if result == "Cor":
                final_result = "Cor"
                fixed_at_iter = it
                if it == 1:
                    fixed_in_1 += 1
                elif it == 2:
                    fixed_in_2 += 1
                else:
                    fixed_in_3 += 1
                break
            if result == "Sem":
                final_result = "Sem"
                became_sem += 1
                break
            current_code = fixed_code
            current_err = new_err or ""

        if final_result == "Syn":
            still_syn += 1
        results.append({
            "id": syn_id,
            "final": final_result,
            "fixed_at_iter": fixed_at_iter,
            "model": args.model,
        })

    if client is not None:
        client.close()

    total = len(results)
    if args.dry_run:
        print("Dry run: would process", total, "items")
        return

    fixed_under_3 = fixed_in_1 + fixed_in_2 + fixed_in_3
    print("\n=== Syn fix results (LLM) ===")
    print("Subfolder:", subfolder)
    print("Model:", args.model)
    print("Total Syn to fix:", total)
    print("Fixed(1 iter):", fixed_in_1)
    print("Fixed(2 iter):", fixed_in_2)
    print("Fixed(3 iter):", fixed_in_3)
    print("Fixed(<3):", f"{fixed_under_3}/{total}")
    print("Still Syn:", still_syn)
    print("Became Sem:", became_sem)
    print("\nTable (Syn / Sem headers):")
    print("Model      | Total Syn | Fixed(1) | Fixed(2) | Fixed(3) | Fixed(<3) | Still Syn | Became Sem")
    print("-" * 85)
    by_model: Dict[str, list] = {}
    for r in results:
        if r.get("dry_run"):
            continue
        model = r["id"].rsplit("_", 2)[0] if "_" in r["id"] else r["id"]
        by_model.setdefault(model, []).append(r)
    for model in sorted(by_model.keys()):
        rows = by_model[model]
        t = len(rows)
        f1 = sum(1 for r in rows if r.get("fixed_at_iter") == 1)
        f2 = sum(1 for r in rows if r.get("fixed_at_iter") == 2)
        f3 = sum(1 for r in rows if r.get("fixed_at_iter") == 3)
        still = sum(1 for r in rows if r.get("final") == "Syn")
        sem = sum(1 for r in rows if r.get("final") == "Sem")
        fu3 = f1 + f2 + f3
        print(f"{model:10} | {t:9} | {f1:8} | {f2:8} | {f3:8} | {fu3}/{t:8} | {still:9} | {sem:10}")
    print("-" * 85)
    print(f"{'Total':10} | {total:9} | {fixed_in_1:8} | {fixed_in_2:8} | {fixed_in_3:8} | {fixed_under_3}/{total:8} | {still_syn:9} | {became_sem:10}")

    summary = {
        "total": total, "fixed_in_1": fixed_in_1, "fixed_in_2": fixed_in_2, "fixed_in_3": fixed_in_3,
        "still_syn": still_syn, "became_sem": became_sem,
    }
    out_json = syn_fix_log_dir / "syn_fix_results.json"
    out_json.write_text(json.dumps({"subfolder": subfolder, "results": results, "summary": summary}, indent=2), encoding="utf-8")
    print("\nResults and prompts saved under:", syn_fix_log_dir)
    print("JSON:", out_json)

    # LaTeX snippet for "Section of results" (Syn / Sem headers)
    fu3 = fixed_in_1 + fixed_in_2 + fixed_in_3
    tex = (
        "\\begin{table}[h]\n"
        "\\centering\n"
        "\\caption{LLM syntax fix: Original Syn $\\rightarrow$ Cor / Syn / Sem (%s)}\n"
        "\\label{tab:syn_fix_%s}\n"
        "\\begin{tabular}{|l|r|r|r|r|r|r|r|}\n"
        "\\hline\n"
        "Model & Total Syn & Fixed(1) & Fixed(2) & Fixed(3) & Fixed($<$3) & Still Syn & Became Sem \\\\\n"
        "\\hline\n"
    ) % (subfolder.replace("_", " "), subfolder.replace("_", "").lower())
    for model in sorted(by_model.keys()):
        rows = by_model[model]
        t = len(rows)
        f1 = sum(1 for r in rows if r.get("fixed_at_iter") == 1)
        f2 = sum(1 for r in rows if r.get("fixed_at_iter") == 2)
        f3 = sum(1 for r in rows if r.get("fixed_at_iter") == 3)
        still = sum(1 for r in rows if r.get("final") == "Syn")
        sem = sum(1 for r in rows if r.get("final") == "Sem")
        fu3_m = f1 + f2 + f3
        tex += f"{model} & {t} & {f1} & {f2} & {f3} & {fu3_m}/{t} & {still} & {sem} \\\\\\\\\n\\hline\n"
    tex += f"Total & {total} & {fixed_in_1} & {fixed_in_2} & {fixed_in_3} & {fu3}/{total} & {still_syn} & {became_sem} \\\\\\\\\n\\hline\n"
    tex += "\\end{tabular}\n\\end{table}\n"
    tex_path = syn_fix_log_dir / "syn_fix_table.tex"
    tex_path.write_text(tex, encoding="utf-8")
    print("LaTeX table:", tex_path)


if __name__ == "__main__":
    main()
