# Anvil: LLM-Powered Synthesis, Validation, and Repair of Alloy Specifications

Archived on Zenodo: [![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20838661.svg)](https://doi.org/10.5281/zenodo.20838661)

This artifact accompanies the MODELS 2026 paper *"Anvil: LLM-Powered Synthesis, Validation, and Repair of Alloy Specifications"* (Yang Hong, Chenbo Yin, Shan Jiang, Yulei Fu, Sarfraz Khurshid).

The artifact supports three research questions:

- **RQ1 - Generation**: re-score stored LLM outputs for English-to-Alloy and Alloy-to-Alloy synthesis.
- **RQ2 - Validation**: reproduce the WithTest vs NoTest validation experiments for E2A and A2A.
- **RQ3 - Repair**: classify faulty Alloy models and run ARepair on semantically incorrect cases.

The verified reproduction path uses stored LLM outputs. No LLM API key is needed unless you intentionally regenerate new LLM outputs, which is outside the verified path.

## Badges Claimed

This artifact claims:

- **Artifact Evaluated - Functional**
- **Artifacts Available**

See `STATUS.md` for details. We do not claim the post-publication "Results Validated" badge.

## Repository Structure

```text
anvil-artifact/
  README.md, STATUS.md, REQUIREMENTS.md, LICENSE
  paper.pdf                    <- Accepted paper PDF for the submission package.
  RQ1_Generation/run.sh         <- Final RQ1 entrypoint.
  RQ2_Validation/run.sh         <- Final RQ2 entrypoint; test-suite validation is fixed.
  RQ3_Repair/run.sh             <- Final RQ3 entrypoint; check-one classification is fixed.
  ARepair/                      <- Vendored ARepair copy, preserving upstream MIT license.
  src/, pom.xml, lib/           <- Java evaluation harness and Alloy 4.2 runtime.
  Dockerfile.arepair
  docker-compose.arepair.yml    <- Dockerized ARepair environment.
  result/Gemini/                <- Stored LLM responses and reproduced outputs.
  query/Gemini/                 <- Prompt/query inputs for optional regeneration.
  scripts/compare_paper_artifact.py
  logs/orchestration/           <- Verification logs and latest paper/artifact diff.
```

Historical debugging wrappers and intermediate logs are preserved under `logs/orchestration/_dev_history/` for transparency, but they are not part of the reviewer-facing reproduction path.

## Environment Setup

Install Java, Maven, Python, Docker, and Docker Compose as described in `REQUIREMENTS.md`.

From the artifact root:

```bash
cd anvil-artifact
mvn -q compile
docker compose -f docker-compose.arepair.yml build arepair
```

The Docker image is required for ARepair-based repair stages. Quick-start commands avoid slow repair work where possible.

## Quick Start

The following commands exercise all three final entrypoints using stored outputs. They completed successfully in the artifact validation run recorded at `logs/orchestration/consolidate_final_scripts_report.log`.

```bash
cd anvil-artifact
bash RQ1_Generation/run.sh --quick
bash RQ2_Validation/run.sh --quick
bash RQ3_Repair/run.sh --quick
```

Expected high-level output:

```text
RQ1 quick completed. Outputs under logs/quick_start/RQ1/gemini-3.1-flash-lite-preview_Function/{E2A,A2A}.
RQ2 quick completed.
RQ3 quick completed.
```

The quick runs use:

- RQ1: `gemini-3.1-flash-lite-preview`, property `Function`, E2A and A2A.
- RQ2: `gemini-3.1-flash-lite-preview`, benchmark `arr`, validation fixed to `AREPAIR_VALIDATION=testsuite`, repair skipped.
- RQ3: `gemini-3.1-flash-lite-preview`, classification only, using `Example --check-one` as the primary classifier.

## Reproducing the Paper's Full Results

Run these commands from `anvil-artifact/`.

```bash
bash RQ1_Generation/run.sh --full
bash RQ2_Validation/run.sh --full
bash RQ3_Repair/run.sh --full
```

Approximate runtimes on the authors' development machine:

- RQ1 full re-scoring: minutes.
- RQ2 full validation and repair: several hours; Docker is used for ARepair repair.
- RQ3 full classification and repair: several hours; Docker is required for ARepair repair.

The final entrypoints intentionally hide debug-era options:

- RQ2 always uses the verified test-suite validation criterion.
- RQ3 always uses `Example --check-one` as the primary classification source, with test-suite and predicate-equivalence checks retained only as diagnostics in `classification.json`.

## Verifying Against the Paper

After running the reproduction scripts, compare artifact outputs with the paper tables:

```bash
python3 scripts/compare_paper_artifact.py
```

The latest completed verification produced:

```text
Combined: 1687/1692 matched; mismatches=5
RQ1: 264/264 matched; mismatches=0
RQ2: 1047/1050 matched; mismatches=3
RQ3: 376/378 matched; mismatches=2
```

Machine-readable summaries are in:

- `logs/orchestration/paper_artifact_diff_latest_summary.json`
- `logs/orchestration/paper_artifact_diff_latest.csv`
- `RQ1_Generation/comparison/diff_report.csv`
- `RQ2_Validation/comparison/diff_report.csv`
- `RQ3_Repair/comparison/diff_report.csv`

## Known Discrepancies

The final comparison has 5 mismatches out of 1692 checked data points.

1. **RQ2 total-row transcription error**. In the paper's A2A Flash-Lite NoTest total, the paper reports `Cor=118`; the artifact and the sum of the paper's own per-row entries give `Cor=116`. This also affects the total repair count shown for the same NoTest column.

2. **RQ2 single repair run-to-run difference**. For `dll-ConsistentPreAndNxt` / Flash-Lite / A2A / NoTest, one ARepair case (`dll_ConsistentPreAndNxt_5`) repaired successfully in the final rerun, giving `Rep=4` where the paper reports `Rep=3`. The input model and test suite are unchanged; this is a single-case repair outcome difference.

3. **RQ3 repair run-to-run difference**. For `student-Contains` / Pro / LLM repair, one ARepair case repaired successfully in the final rerun, giving `1/10` where the paper reports `0/10`. This changes the Pro total from `62/129` to `63/129`.

Together, the RQ2 and RQ3 repair differences affect 4 table cells, less than 0.2% of all checked data points. These differences are consistent with known run-to-run variability in SAT-solver-based repair and test-generation workflows; see, for example, Gutiérrez Brida et al., "ICEBAR: Feedback-Driven Iterative Repair of Alloy Specifications", ASE 2022, which discusses nondeterminism and solver-related variability in Alloy repair workflows.

The historically discussed `183/369` vs `181/369` RQ3 repair accounting is a denominator-definition issue: two repaired cases are syntax-classified edge cases rather than Sem cases. The artifact's strict table comparison uses the published paper table values and reports only the 2 RQ3 mismatches listed above.

## Known Limitations

- The artifact reproduces the paper using stored LLM outputs. Regenerating LLM outputs requires API credentials and may yield different responses.
- Full RQ2/RQ3 repair runs can take hours because ARepair is invoked in Docker.
- The vendored `ARepair/` directory keeps its upstream license in `ARepair/LICENSE`. Artifact-local patches make the artifact self-contained and remove debug side effects from the reviewer-facing path.

## Artifact Availability

The artifact is archived on Zenodo at https://doi.org/10.5281/zenodo.20838661. GitHub/GitLab alone are not archival repositories for ACM artifact badges, so this GitHub repository is paired with the Zenodo archival DOI.

## License

This artifact is released under the MIT License; see `LICENSE`. The vendored ARepair copy retains its own MIT license in `ARepair/LICENSE`.

## Citation

If you use this artifact, please cite the MODELS 2026 paper. The final BibTeX entry can be added after camera-ready metadata is available.
