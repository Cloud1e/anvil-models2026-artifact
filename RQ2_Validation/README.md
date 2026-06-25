# Moved: WithTest vs NoTest scripts

**RQ1 re-evaluation (thesis):** `evaluate_*.py` default to **`-Darepair.validation=testsuite`** (merged model + benchmark `run … expect` tests — unified with RQ2/RQ3). Set **`AREPAIR_VALIDATION=equivalence`** for bounded `check { P <=> P2 }` only. Labels (Correct / Syntax / Wrong) still come from `AlloyProcess` on the built module.

Scripts are split into two subfolders under this directory:

- **English-to-Alloy** → `scripts/with_vs_without_test/english_to_alloy/`
  - ARepair / ARepairNoTest (prompt = natural language)
  - Run: `bash scripts/with_vs_without_test/english_to_alloy/run_with_vs_no_test.sh`

- **Alloy-to-Alloy** → `scripts/with_vs_without_test/alloy_to_alloy/`
  - ARepair_Alloy2Alloy_WithTest / ARepair_Alloy2Alloy_NoTest (prompt = human-correct body)
  - Run: `bash scripts/with_vs_without_test/alloy_to_alloy/run_with_vs_no_test_alloy2alloy.sh`

See each folder’s README for details.
