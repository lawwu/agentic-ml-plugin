---
name: build-baseline
description: Builds and evaluates non-ML baselines (majority class, mean predictor, simple rules, naive forecasting) to establish the performance floor that ML must beat. Use when asked to build a baseline, establish a heuristic baseline, create a non-ML baseline, or before training a model to satisfy Rule 1 of Google's Rules of ML. Run this automatically after plan-experiment and before any model training begins.
argument-hint: "<objective> --data SOURCE --label-col COL --metric METRIC [--split validation|test] [--out-dir DIR] [--run-id ID]"
---

# Build Baseline

Construct and evaluate non-ML baselines to establish the performance floor that any ML model must beat before being considered worthwhile.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<objective>` — plain-language description of the prediction goal
- `--data SOURCE` — dataset path, HuggingFace dataset, or DB target
- `--label-col COL` — target column name
- `--metric METRIC` — primary evaluation metric (e.g. `f1`, `auprc`, `rmse`, `ndcg`)
- `--split` — evaluation split (default: `validation`; use `test` only if no validation split exists)
- `--out-dir DIR` — output directory (default: `./`)
- `--run-id ID` — run ID to attach to artifact (set by `orchestrate-e2e`; else generate locally)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Load the dataset and identify the task type

Load the data from `--data` and inspect:

- Label column distribution (`--label-col`)
- Column dtypes and sample values
- Row counts per split

Classify the task as one of:

- **classification** — discrete label with finite cardinality
- **regression** — continuous numeric target
- **ranking** — labels express preference or relevance order
- **forecasting** — time-ordered target with temporal structure

If task type is ambiguous, state your assumption and explain it.

### 2. Build non-ML baselines appropriate to the task type

Use `uv run python` for all computation. Do not use pre-trained ML models — baselines must be fully non-ML.

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

Build all methods applicable to the detected task type. Skip methods that cannot be computed from the available data (e.g., `seasonal-naive` when no seasonal period is detectable) and record the reason.

### 3. Evaluate each baseline on the primary metric

Evaluate on the `--split` set (default: `validation`) using the metric specified in `--metric`.

Supported metrics (use scikit-learn or equivalent):

- **Classification**: `accuracy`, `f1` (macro), `f1_binary`, `auprc`, `roc_auc`, `precision`, `recall`
- **Regression**: `rmse`, `mae`, `mape`, `r2`
- **Ranking**: `ndcg`, `map`, `mrr`
- **Forecasting**: `rmse`, `mae`, `smape`

Show the evaluation command before running it.

### 4. Select the best baseline

- For metrics where higher is better (accuracy, f1, auprc, roc_auc, ndcg, map, r2): select the baseline with the **highest** score.
- For metrics where lower is better (rmse, mae, mape): select the baseline with the **lowest** score.
- Mark the winning method as `is_best: true` in the artifact.

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
Split: <validation|test>

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
- Running baseline computations on the validation split
- Writing the JSON artifact and any summary outputs

Require user approval before:

- Evaluating on the test split
- Modifying or writing back to the source data

### 7. Stop conditions

Stop when:

- A complete baseline report is produced and `build-baseline.json` is written, or
- The dataset cannot be loaded (report the specific error and stop), or
- No baseline method can be computed (report why and stop)

## Quick heuristics

- Majority-class score suspiciously high (> 0.9) → check for severe class imbalance; flag as `high` finding
- Single-feature threshold beats all other baselines by large margin → that feature may be a leakage proxy; flag for `review-target` re-check
- Baseline outperforms a subsequently trained ML model → ML model likely has a bug, data issue, or the problem does not warrant ML (Rule 1 of Google's Rules of ML)
- No validation split available → fall back to 80/20 train/validation split from training data; document assumption

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
      "description": "<what it does>",
      "score": 0.731,
      "is_best": true
    }
  ],
  "best_baseline": "<method name>",
  "best_score": 0.731
}
```

See [../../references/schemas.md](../../references/schemas.md) for the full schema definition.
