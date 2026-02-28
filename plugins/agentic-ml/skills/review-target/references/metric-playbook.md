# Metric Playbook

Choose metrics that match the decision and class balance.

## Classification

- Balanced classes, thresholded action: `accuracy` + `f1`
- Imbalanced positive class: `auprc` (primary), `roc_auc` (secondary)
- Ranking/prioritization use case: `precision@k`, `recall@k`
- Calibration-sensitive decisions: add `brier` or calibration error checks

## Regression

- Outlier-sensitive cost: `mae`
- Large-error penalty priority: `rmse`
- Relative error matters: `mape` (only when target values are strictly positive and non-near-zero)

## Forecasting / time series

- Scale-aware: `mae`, `rmse`
- Scale-free comparison: `mase` or `smape`
- Operational guardrail: bias (`mean forecast error`) and prediction interval coverage

## Threshold policy

- Define decision threshold separately from model metric.
- Select threshold on validation data only.
- Report tradeoff table: precision/recall or cost matrix at candidate thresholds.

## Baselines

Always compare to at least one baseline:

- Classification: majority class and simple logistic model
- Regression: mean/median predictor
- Forecasting: naive seasonal/last-value baseline
