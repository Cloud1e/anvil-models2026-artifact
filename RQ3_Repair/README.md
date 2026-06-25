# RQ3 — Faulty Alloy-to-Alloy rewrite + ARepair

End-to-end: LLM rewrites the body of each **single-fault** predicate (still faulty), then Java classifies originals + rewrites (Cor/Syn/Sem), then **ARepair** runs on originals and on each LLM rewrite.

## Prerequisites

- `GOOGLE_API_KEY` or `GEMINI_API_KEY` (host LLM step)
- Docker + `docker-compose.arepair.yml` (ARepair steps)
- Prompts under `query/Gemini/ARepair_FaultyRewrite/<model>/<Predicate>.txt` and originals under `ARepair/experiments/models/original_faulty_models/`
- **Python package `google-genai`** on the interpreter that runs the host steps (`run_faulty_rewrite.py`, `classify_faulty_models.py`). Host-side scripts call **`python`** (not `python3`) so `conda activate lab` picks your env. If you see `ModuleNotFoundError: No module named 'google'`:

  ```bash
  conda activate lab
  bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --model gemini-3-flash-preview
  ```

  Or: `conda run -n lab bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --model gemini-3-flash-preview`

  Install into the active env if needed: `pip install google-genai`.

  **Note:** ARepair steps **inside Docker** still use `python3` (Ubuntu image); only the host LLM + classify steps use `python`.

## Run (from repo root)

Outputs are **per Gemini model** (no overwrite across models):

`result/Gemini/RQ3_Repair/FaultyRewrite/<gemini-model>/`

### Classification-only (recommended for re-evaluation)

If you only want to **classify** existing models as **Cor / Syn / Sem** (no LLM generation, no ARepair),
the pipeline script now defaults to **Step 1.5 only**:

```bash
bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh --model gemini-3-flash-preview
```

This reads existing `repair_info_original.json` and `repair_info_llm.json` under the corresponding output
directory and (re)writes `classification.json`.

To **avoid overwriting** a previous run of the *same* model, use a unique `--run-tag` (writes under `.../<model>/runs/<tag>/`):

```bash
bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh \
  --model gemini-3-flash-preview \
  --run-tag "$(date +%Y%m%d_%H%M%S)"
```

Or set `--out-root` to any new directory yourself.

### Full pipeline (LLM generation + classification + ARepair)

To run the original end-to-end pipeline (generate rewrites, classify, and run ARepair), use:

```bash
bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh \
  --model gemini-3-flash-preview \
  --full
```

Or enable steps explicitly:

```bash
bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh \
  --model gemini-3-flash-preview \
  --run-llm --run-arepair
```

### Gemini 3.0 Flash

```bash
bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh \
  --model gemini-3-flash-preview
```

### Gemini 3.1 Flash Lite

```bash
bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh \
  --model gemini-3.1-flash-lite-preview
```

Optional smoke test: `--limit 1` (first faulty case only).  
Reuse cached LLM responses and only re-run classify: `--skip-llm` (this is also the default now).
Skip ARepair explicitly (default): `--skip-arepair`.

Custom output root (must match what you pass into Docker):

```bash
bash scripts/thesis/RQ2_FaultyRewrite_ARepair/run_faulty_rewrite_pipeline.sh \
  --model gemini-3-flash-preview \
  --out-root result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3-flash-preview
```

## Fill Table E in the paper

After both runs finish, aggregate **Flash / Flash Lite** columns (and verify Pro) with:

```bash
python scripts/thesis/RQ2_FaultyRewrite_ARepair/summarize_table_e.py --flash --lite
# or one model:
python scripts/thesis/RQ2_FaultyRewrite_ARepair/summarize_table_e.py \
  --info-root result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3-flash-preview
```

**Separate LaTeX files (do not overwrite previous exports):** each model gets its own file under `result/`:

```bash
python scripts/thesis/RQ2_FaultyRewrite_ARepair/summarize_table_e.py --flash --lite --write-tex
# -> result/table_e_rq3_faulty_gemini-3-flash-preview.tex
# -> result/table_e_rq3_faulty_gemini-3.1-flash-lite-preview.tex
```

Optional run id in the filename: `--tex-suffix run20260322` → `..._gemini-3-flash-preview_run20260322.tex`.  
Custom directory: `--tex-dir result/tables_rq3`.  
Exact path: `--output-tex /tmp/flash_fragment.tex` (single `--info-root` only).

The script prints a LaTeX fragment: **Cor, Syn, Sem** (LLM 10×), **Orig** (repaired/total Sem for the shared original faulty model), **LLM** (repaired/total Sem among LLM rewrites).  
**Orig** should match the **Gemini 3.1 Pro** column for each row (same `original_faulty_models`); copy from Pro if you prefer.

If you used `--run-tag`, point `--info-root` at that run folder, e.g.  
`result/Gemini/RQ3_Repair/FaultyRewrite/gemini-3-flash-preview/runs/20260322_153045`.

## Related scripts

| Script | Role |
|--------|------|
| `run_faulty_rewrite_pipeline.sh` | Host LLM + classify + Docker ARepair |
| `run_faulty_rewrite.py` | LLM calls + write `repair_info_*.json` + `models/llm_faulty_models/` |
| `classify_faulty_models.py` | 默认 **`Rq3ParallelTestSuiteOracle`**（`repair_info` 里的 `model` + `test_suite`），与 RQ1 学长侧 **testsuite**、RQ3 测试套件判定一致；`--legacy-check-one` 为旧版仅 `Example --check-one`。→ `classification.json` |
| `summarize_table_e.py` | Build Table E numbers from `classification.json` + `repair_results.json` |
