# Changelog

All notable changes to this project are documented here.

The format follows the categories used in the automated release workflow (`.github/workflows/release.yml`): **Skills & Features**, **Bug Fixes**, **Documentation**, **Maintenance**. Releases correspond to tags in the repository and version entries in `plugins/agentic-ml/.claude-plugin/plugin.json`.

---

## [Unreleased]

---

## [0.4.0] — 2026-11-04

### 🛠 Skills & Features

- feat: add `select-approach` skill (gate 0) — decides between no ML, supervised, forecasting, unsupervised, embeddings, LLM prompting/RAG, LLM fine-tuning, RLHF/DPO/RLVR, and agents, cheapest first, and maps which lifecycle skills apply
- feat: add `check-deployment-readiness` skill (gate 9) — packages the model with a signature, checks training/serving parity in a fresh process, latency/memory budgets, and the data contract, and writes monitoring, rollout, and rollback plans (`serving_check.py`)
- feat: user levels (`junior` / `senior` / `staff`) via `--level` or `.claude/agentic-ml.local.md`, with autonomy settings and review cards; level changes communication and pauses, never thresholds
- feat: evaluation protocol — `review-target` creates the split once and locks the test set (`make_splits.py`); `check-eval` reports bootstrap confidence intervals, paired baseline deltas, slices, calibration, and the operating point (`eval_report.py`), and runs the one-time final test evaluation with a hash check
- feat: provenance (git, packages, lockfiles, data hashes, seed) in every artifact that touches data or code (`scripts/provenance.py`)
- feat: `train-model` pre-flight checks (init loss, overfit one batch, save/resume, too-good-to-be-true), native early stopping, Optuna sweeps tuned on validation/CV only, experiment-tracker logging, and a leakage-safe tabular training scaffold (`train_tabular.py`)
- feat: tabular track in `check-data-pipeline` (preprocessing fit on train only, out-of-fold target encoding, resampling inside folds, unseen categories, column contract)
- feat: `check-dataset-quality` saves a data contract and drift baseline (`data_contract.py`, with PSI validation) and scans for personal data
- feat: `build-baseline` fits on train and scores on validation only, saves predictions for paired comparison, and adds statistical and zero-shot time-series foundation-model baselines (Chronos, TimesFM, Moirai) for forecasting
- feat: `orchestrate-e2e` runs gates 0–10, pauses by autonomy level, makes the final test evaluation part of a signed-off promotion decision, and scores each run against Google's ML Test Score rubric
- feat: base schema 1.1 adds `level`, `provenance`, `evidence_notebook`/`evidence_blocks`, and optional `findings[].evidence`
- feat: evidence notebook across all skills — each skill appends the commands behind its headline numbers and `blocker`/`high` findings, with real outputs, to one showboat notebook per run (`evidence.md`); `orchestrate-e2e` verifies it before promotion, and a changed block blocks an unqualified GO. `demonstrate-value` now records into the same notebook instead of a separate `value-demo.md`
- feat: reorder lifecycle gates so the dataset audit runs before anything is computed on the data: target → dataset quality → baseline → experiment plan → (feature-engineer) → pipeline; `plan-experiment` now reads `build-baseline.json` and the dataset profile
- feat: `orchestrate-e2e` now invokes `feature-engineer` (optional gate 4b) for raw data, documents `--business-context`, and defines a CONDITIONAL policy so caveats are carried into the final summary
- feat: `demonstrate-value` records every figure in a showboat evidence document (`showboat exec` / `showboat verify`) and computes business impact from an operating point with labeled assumptions
- feat: `recommend-new-approaches` prepares an autoresearch `program.md` for ideas that fit its fixed-budget loop and surfaces the launch as `needs-approval`

### 🐛 Bug Fixes

- fix: skill script commands use `${CLAUDE_SKILL_DIR}` so they resolve when the plugin is installed; report viewer moved to `skills/orchestrate-e2e/scripts/`
- fix: remove non-existent commands (`showboat generate`, `autoresearch --max-papers`)
- fix: replace the non-existent `hard-attrition` benchmark scenario with `hard-readmission`; document `easy` and `medium` demo scenarios
- fix: slash-command examples use the `/agentic-ml:` namespace
- fix: broken schema/vocabulary links in `artifact-contract.md`
- fix: schema drift — `recommend-new-approaches` gate name, `EARLY_STOPPED`/`TIMEOUT` terminal states, canonical severities in `explain-model`, numeric-to-enum confidence mapping
- fix: training retries apply to gate 6, matching `--max-retries`; AutoML stage numbering in benchmark modes
- fix: all Python scripts declare dependencies with PEP 723 headers so `uv run` works in a fresh environment
- fix: `feature_importance.py` handles shap's 3-D classifier output and multiclass models, falling back to permutation importance
- fix: `compare-results.sh` treats loss/perplexity/error metrics as lower-is-better, compares only matching metric names, and reads flat HF results
- fix: `check-process.sh` matches full command lines, reports SSH failures as errors instead of "dead", and no longer creates a `.venv` in the user's project
- fix: remote log scripts use `ssh -n`, safe quoting, and `~/` expansion
- fix: report viewer loads every skill's artifact, shows CONDITIONAL distinctly, escapes all artifact text (XSS), and tolerates malformed artifacts
- fix: `profile-dataset.py` handles pandas 3 string dtype, nested JSONL, continuous labels, and empty directories
- fix: demo generators take `--out` (default: next to the script); hard-fraud no longer allocates a 20k×20k matrix and now injects the documented unreviewed-fraud label noise
- fix: release notes no longer drop the oldest commit; frontmatter validator checks `name` matches the directory and description length, and no longer interpolates filenames into shell

### 📚 Documentation

- docs: README quickstart generates demo data first; plugin and marketplace descriptions cover the full lifecycle
- docs: AGENTS.md script conventions (`${CLAUDE_SKILL_DIR}`, PEP 723 headers, no side effects in the user's project)

---

## [0.3.0] — 2026-03-18

### 🛠 Skills & Features

- feat: add `recommend-new-approaches` skill — generates prioritized research directions, modeling ideas, and loss function modifications from training artifacts; optionally leverages [autoresearch](https://github.com/karpathy/autoresearch)
- feat: integrate `recommend-new-approaches` as step 5d in `orchestrate-e2e` (always runs after eval/interpretability gates, before promotion decision)

### 📚 Documentation

- docs: add stage-order column to Available Skills table in README
- docs: clarify `babysit-training` can be invoked standalone when training is already running
- docs: add `CHANGELOG.md` and document update convention in `AGENTS.md`

---

## [0.2.0] — 2026-02-27

### 🛠 Skills & Features

- feat: add `train-model` skill — launches and manages training with early stopping, HP config, and checkpoint management; delegates monitoring to `babysit-training`
- feat: add `demonstrate-value` skill — synthesizes evaluation and explainability results into a stakeholder-ready HTML presentation using showboat
- feat: add exponential backoff in `babysit-training` monitoring loop to reduce polling overhead on long runs

### 🔧 Maintenance

- chore: bump `actions/checkout` to v6

---

## [0.1.0] — 2026-01-01

Initial release.

### 🛠 Skills & Features

- feat: `review-target` — validate label/target definition, leakage risk, metric alignment, and split strategy
- feat: `plan-experiment` — design a structured experiment plan with hypothesis, model candidates, HP search space, and compute budget
- feat: `build-baseline` — build and evaluate non-ML baselines to establish the performance floor
- feat: `check-dataset-quality` — profile and validate datasets (CSV, Parquet, JSONL, HuggingFace, image dirs, DB tables)
- feat: `check-data-pipeline` — dry-run a preprocessing pipeline on a small sample to catch shape/dtype/label issues
- feat: `feature-engineer` — explore data sources and design leakage-safe feature sets
- feat: `babysit-training` — continuously monitor a training run (local, SSH, Vertex AI) until terminal state
- feat: `check-failed-run` — diagnose failed/unstable runs, classify root causes, produce recovery plan
- feat: `check-eval` — evaluate a checkpoint via HF Trainer, lm-evaluation-harness, or custom script
- feat: `explain-model` — generate feature importance, bias audit, and model card
- feat: `orchestrate-e2e` — coordinate the full ML lifecycle with explicit stage gates and Go/No-Go decision
- feat: `benchmark-e2e` — compare no-plugin/plugin/automl workflow approaches across ML scenarios
- feat: JSON artifact schema and canonical vocabulary shared across all skills
- feat: HTML report viewer (`report-viewer/generate_report.py`) for gate timelines and per-skill findings
- feat: automated GitHub release workflow with conventional-commit categorisation
