# Changelog

All notable changes to this project are documented here.

The format follows the categories used in the automated release workflow (`.github/workflows/release.yml`): **Skills & Features**, **Bug Fixes**, **Documentation**, **Maintenance**. Releases correspond to tags in the repository and version entries in `plugins/agentic-ml/.claude-plugin/plugin.json`.

---

## [Unreleased]

### 🛠 Skills & Features

- feat: add `recommend-new-approaches` skill — generates prioritized research directions, modeling ideas, and loss function modifications from training artifacts; optionally leverages [autoresearch](https://github.com/karpathy/autoresearch)
- feat: integrate `recommend-new-approaches` as step 5d in `orchestrate-e2e` (always runs after eval/interpretability gates, before promotion decision)

### 📚 Documentation

- docs: add stage-order column to Available Skills table in README
- docs: clarify `babysit-training` can be invoked standalone when training is already running

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
