# Alloy-to-Alloy (WithTest vs NoTest)

Scripts for the **Alloy-to-Alloy** experiment: prompt = original human-correct predicate body; LLM produces equivalent but syntactically different solutions.

**Correct model source:** `ARepair/experiments/models/<model>.als` (human-written). To use the upstream version: `cd ARepair && git pull`.

**Validation:** `evaluate_alloy2alloy_responses.py` defaults to **testsuite** (same as `run_rq1_a2a_full_host.sh`). Set `AREPAIR_VALIDATION=equivalence` for bounded equivalence only. Same `AlloyProcess` labeling. `-Darepair.check.scope=N` optional.

- **generate_alloy2alloy_prompts.py** – Generate WithTest and NoTest prompts (from ARepair/experiments/models).
- **evaluate_alloy2alloy_responses.py** – Evaluate WithTest and NoTest responses via Java.
- **compare_with_vs_without_test_alloy2alloy.py** – Compare Cor/Syn/Sem and Rep; write LaTeX. Use `--tex-suffix <id>` to write `..._by_predicate_<id>.tex` (pipeline passes Gemini model id when `--model` is set).
- **run_with_vs_no_test_alloy2alloy.sh** – Full flow: evaluate, compare, optional ARepair, compare again.
- **fix_syntax_llm.py** – LLM-based syntax fix: use Alloy parser error message, up to 3 iterations; saves prompts/responses locally. Table headers: Syn, Sem.

**WithTest vs NoTest are separate:** Java is run twice with different subfolders; each run reads its own `responses/` and writes its own `Alloy/` (and `Alloy/SynItems/` when there are syntax errors). No shared overwriting.

**LLM syntax fix (optional):** After evaluation, Syn items are under `result/Gemini/<subfolder>/Alloy/SynItems/*.als` and `*.err`. Run `fix_syntax_llm.py ARepair_Alloy2Alloy_WithTest` and/or `fix_syntax_llm.py ARepair_Alloy2Alloy_NoTest`. Uses Gemini (default `gemini-1.5-flash` for lower cost). All prompts and responses are saved under `result/Gemini/<subfolder>/SynFixLog/` for inspection and manual testing. Output: Fixed(1/2/3), Fixed(<3) e.g. 3/5, Still Syn, Became Sem; LaTeX table in `SynFixLog/syn_fix_table.tex`.

Data: `result/Gemini/ARepair_Alloy2Alloy_WithTest/`, `result/Gemini/ARepair_Alloy2Alloy_NoTest/`. LaTeX default: `result/thesis/RQ1_TestVsNoTest/tables/with_vs_no_test_alloy2alloy_by_predicate.tex`; with `--model` / `--tex-suffix`: `result/thesis/RQ1_TestVsNoTest/tables/with_vs_no_test_alloy2alloy_by_predicate_<suffix>.tex`.
