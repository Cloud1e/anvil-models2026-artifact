# English-to-Alloy (WithTest vs NoTest)

Scripts for the **English-to-Alloy** experiment: prompt = natural language + model; WithTest includes test suite, NoTest does not.

**Validation:** `evaluate_*` defaults to **testsuite** (unified thesis). Set `AREPAIR_VALIDATION=equivalence` for bounded equivalence only. Labels from `AlloyProcess`. Scope: `-Darepair.check.scope=N` (default 5).

- **generate_arepair_notest_prompts.py** – Generate NoTest prompts from WithTest (strip test suite).
- **evaluate_notest_responses.py** – Evaluate NoTest responses via Java (`-Darepair.result.subfolder=ARepairNoTest`; no copy/restore).
- **compare_with_vs_without_test.py** – Compare C/SE/W and Rep by model-predicate; write LaTeX. Use `--tex-suffix <id>` for `..._by_predicate_<id>.tex` (pipeline passes `--model` / `basename --out-root` on Step 5).
- **restore_withtest_alloy.sh** – Re-run WithTest evaluation (Java default subfolder=ARepair).
- **run_with_vs_no_test.sh** – Full flow: evaluate NoTest, compare, ARepair both, compare again.

Data: `result/Gemini/ARepair/` (WithTest), `result/Gemini/ARepairNoTest/` (NoTest). LaTeX default: `result/thesis/RQ1_TestVsNoTest/tables/with_vs_no_test_by_predicate.tex`; with `--model` in `run_with_vs_no_test.sh`: `result/thesis/RQ1_TestVsNoTest/tables/with_vs_no_test_by_predicate_<suffix>.tex`.
