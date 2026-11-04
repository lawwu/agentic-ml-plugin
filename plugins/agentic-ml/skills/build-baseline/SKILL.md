---
name: build-baseline
description: Builds and evaluates non-ML baselines (majority class, mean predictor, simple rules, naive forecasting) to establish the performance floor that ML must beat. For forecasting, also runs statistical models and a zero-shot time-series foundation model (Chronos, TimesFM, Moirai) as reference baselines. Use when asked to build a baseline, establish a heuristic baseline, create a non-ML baseline, or before training a model to satisfy Rule 1 of Google's Rules of ML. Run this automatically after check-dataset-quality and before plan-experiment, so the plan's success criteria are set against a real baseline score.
argument-hint: "<objective> --data SOURCE --label-col COL --metric METRIC [--split validation|test] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Build Baseline

Construct and evaluate non-ML baselines to establish the performance floor that any ML model must beat before being considered worthwhile.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<objective>` — plain-language description of the prediction goal
- `--data SOURCE` — dataset path, HuggingFace dataset, or DB target
- `--label-col COL` — target column name
- `--metric METRIC` — primary evaluation metric (e.g. `f1`, `auprc`, `rmse`, `ndcg`)
- `--split` — evaluation split (default and only allowed value: `val`; the test split is reserved for the final evaluation in `check-eval`)
- `--out-dir DIR` — output directory (default: `./`)
- `--run-id ID` — run ID to attach to artifact (set by `orchestrate-e2e`; else generate locally)

Target: `$ARGUMENTS`

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- `junior`: explain why the baseline matters (Rule 1 of the Rules of ML) and what "score to beat" means.
- All levels build the same baseline suite.

## Your responsibilities

### 1. Load the dataset and identify the task type

Load the data from `--data` and the split from `<out-dir>/splits/split_assignments.csv` (created by `review-target`). If no split exists, create one with `review-target`'s `make_splits.py` using the strategy in `review-target.json` — never a random 80/20 split when the data has timestamps or repeated entities.

Follow [../../references/evaluation-protocol.md](../../references/evaluation-protocol.md): **fit every baseline on `train` rows only, score it on `val`, and never read `test` rows.**

Inspect:

- Label column distribution (`--label-col`) in `train` and `val`
- Column dtypes and sample values
- Row counts per split

Classify the task as one of:

- **classification** — discrete label with finite cardinality
- **regression** — continuous numeric target
- **ranking** — labels express preference or relevance order
- **forecasting** — time-ordered target with temporal structure

If task type is ambiguous, state your assumption and explain it.

### 2. Build non-ML baselines appropriate to the task type

Use `uv run python` for all computation. Rule-1 baselines must be fully non-ML: no trained or pre-trained models. Fit their parameters (class frequencies, means, thresholds, rules) on `train` only. For `single-feature-threshold`, choose the feature and threshold on `train` (or by cross-validation within `train`), then score on `val`.

Tag each baseline with a `kind`: `non-ml` (the Rule-1 floor), `statistical`, or `foundation-model` (forecasting reference baselines below).

#### Classification

| Method | Description |
|--------|-------------|
| `majority-class` | Always predict the most frequent class |
| `stratified-random` | Randomly predict class proportional to training frequencies |
| `zero-r` | Alias for majority-class; ZeroR from Weka tradition |
| `single-feature-threshold` | Best single-feature threshold rule (e.g., `age > 45 → class 1`) |

#### Regression

| Method | Description |
|--------|-------------|
| `mean-predictor` | Always predict training set mean |
| `median-predictor` | Always predict training set median |
| `last-value` | For time series: predict last observed value |
| `single-feature-linear` | Best single-feature OLS regression (no regularization) |

#### Ranking

| Method | Description |
|--------|-------------|
| `popularity-rank` | Rank by item frequency in training set |
| `random-rank` | Random ranking (shuffle) |

#### Forecasting

| Method | Description |
|--------|-------------|
| `naive` | Predict last known value |
| `seasonal-naive` | Predict value from same period in previous cycle |
| `moving-average` | Rolling mean over last N observations |

For forecasting, also build these reference baselines. A custom forecasting model has to beat them to be worth maintaining:

| Method | Kind | Description |
|--------|------|-------------|
| `ets` / `auto-arima` / `theta` | `statistical` | Classical models, e.g. via `statsforecast` (`uv run --with statsforecast`) |
| `tsfm-zero-shot` | `foundation-model` | A pre-trained time-series foundation model forecasting without training on this data — e.g. Amazon Chronos / Chronos-Bolt (`chronos-forecasting`), Google TimesFM (`timesfm`), or Salesforce Moirai (`uni2ts`) |

Foundation-model notes:

- Prefer a small checkpoint that runs on CPU.
- Feed only history available at each forecast origin.
- Use the same backtest windows and horizon as every other baseline.
- Record the model ID and version.
- Check the model's license before relying on it in production.
- Do not call a hosted forecasting API unless the user confirms data may leave the network.
- If the model cannot be installed or run, record `SKIPPED` with the reason.

Build all methods applicable to the detected task type. Skip methods that cannot be computed from the available data (e.g., `seasonal-naive` when no seasonal period is detectable) and record the reason.

### 3. Evaluate each baseline on the primary metric

Evaluate on `val` using the metric specified in `--metric`.

For every baseline:

- Save its `val` predictions in the [shared predictions format](../../references/evaluation-protocol.md#predictions-file) to `<out-dir>/predictions/baseline_<method>_val.csv`. `check-eval` uses these for a paired comparison with the model.
- Score the file with `uv run "${CLAUDE_PLUGIN_ROOT}/skills/check-eval/scripts/eval_report.py" --pred <file> --metric <metric> --out <out-dir>/predictions/baseline_<method>_val.metrics.json` to get the score with a 95% interval.
- Record its fitted parameters as `rule` in the artifact (e.g. `{"predict": 0}` or `{"feature": "age", "threshold": 45}`), so `check-eval --final` can apply the same rule to the test rows once.

Supported metrics (use scikit-learn or equivalent):

- **Classification**: `accuracy`, `f1` (macro), `f1_binary`, `auprc`, `roc_auc`, `precision`, `recall`
- **Regression**: `rmse`, `mae`, `mape`, `r2`
- **Ranking**: `ndcg`, `map`, `mrr`
- **Forecasting**: `rmse`, `mae`, `smape`

Show the evaluation command before running it.

### 4. Select the best baseline

- For metrics where higher is better (accuracy, f1, auprc, roc_auc, ndcg, map, r2): select the baseline with the **highest** score.
- For metrics where lower is better (rmse, mae, mape): select the baseline with the **lowest** score.
- Mark the winning method as `is_best: true` in the artifact. The best is chosen across all kinds — for forecasting, a custom model must beat the statistical and foundation-model baselines too. Report the best `non-ml` method separately in the summary.

The best baseline score is the floor that any ML model must exceed to justify training complexity.

### 5. Report format

```text
Baseline Report
===============
Objective: <...>
Data: <...>
Label col: <...>
Task type: <classification|regression|ranking|forecasting>
Metric: <...>
Split: val (baselines fit on train)

Baselines evaluated:
| Method                  | Score    | Notes                          |
|-------------------------|----------|--------------------------------|
| majority-class          | 0.612    | predicts class 0 always        |
| stratified-random       | 0.489    |                                |
| single-feature-threshold| 0.731  ★ | age > 45 → churn=1 (best)      |
| zero-r                  | 0.612    |                                |

Best baseline: single-feature-threshold (score: 0.731)
Score to beat: 0.731 f1

Decision: GO
```

The `★` marks the winning method. Always report the score to beat in the final line.

### 6. Fix policy

Apply without approval:

- Loading and reading data (read-only)
- Running baseline computations (fit on `train`, score on `val`)
- Writing the JSON artifact and any summary outputs

Never evaluate baselines on the test split; the final test comparison happens once in `check-eval --final`.

Require user approval before:

- Modifying or writing back to the source data
- Calling a hosted forecasting API (data leaves the network)

### 7. Stop conditions

Stop when:

- A complete baseline report is produced and `build-baseline.json` is written, or
- The dataset cannot be loaded (report the specific error and stop), or
- No baseline method can be computed (report why and stop)

## Quick heuristics

- Majority-class score suspiciously high (> 0.9) → check for severe class imbalance; flag as `high` finding
- Single-feature threshold beats all other baselines by large margin → that feature may be a leakage proxy; flag for `review-target` re-check
- Baseline outperforms a subsequently trained ML model → ML model likely has a bug, data issue, or the problem does not warrant ML (Rule 1 of Google's Rules of ML)
- No split available → create one with `make_splits.py` using `review-target`'s strategy; never fall back to a random 80/20 split on time-ordered or entity-repeated data
- Forecasting model fails to beat `tsfm-zero-shot` or `seasonal-naive` → recommend the simpler baseline for production

## Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- the baseline code: save it as `<out-dir>/baselines/build_baselines.py` (fits on `train`, scores `val`) and `exec` it with its output directory set to `"$(mktemp -d)"`, printing the fitted rules and row counts
- per baseline: `eval_report.py --pred predictions/baseline_<method>_val.csv --metric <metric> --out /dev/null | head -1` — the score with its interval
- foundation-model baselines: a note with the model ID and version; `exec` them only if they run in under a minute on CPU, otherwise `exec` a sha256 of their predictions file

## JSON artifact

Write `build-baseline.json` to `--out-dir` (or `./` if invoked standalone) following the base schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

`decision` is always `GO` — baselines are informational and never block the pipeline.

Skill-specific fields to populate (in addition to base schema fields):

```json
{
  "task_type": "classification | regression | ranking | forecasting",
  "data_source": "<path or dataset>",
  "label_col": "<col>",
  "primary_metric": "<metric>",
  "baselines": [
    {
      "method": "<name>",
      "kind": "non-ml | statistical | foundation-model",
      "description": "<what it does>",
      "rule": {"<param>": "<fitted value>"},
      "score": 0.731,
      "ci": [0.69, 0.77],
      "predictions_path": "<out-dir>/predictions/baseline_<method>_val.csv",
      "is_best": true
    }
  ],
  "split_manifest_path": "<out-dir>/splits/split-manifest.json",
  "best_baseline": "<method name>",
  "best_score": 0.731
}
```

See [../../references/schemas.md](../../references/schemas.md) for the full schema definition.
