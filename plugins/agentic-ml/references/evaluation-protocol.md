# Evaluation Protocol

The rules every skill follows so reported numbers can be trusted. They apply at every [level](levels.md). Every headline number is also recorded, with the command that produced it, in the run's [evidence notebook](evidence-notebook.md).

## 1. Split once, lock the test set

- `review-target` creates the split once with [`make_splits.py`](../skills/review-target/scripts/make_splits.py). The strategy must match how the model will be used:
  - `time` — the model scores the future. Add `--gap` when labels mature after a delay.
  - `group` — the same entity (customer, patient, company) appears in several rows.
  - `stratified` — classification with no time or entity structure.
  - `random` — regression with no time or entity structure.
- The split writes `splits/split_assignments.csv` (`row_key,split`) and `splits/split-manifest.json`, which includes `test_keys_sha256`.
- **No skill reads test rows except the final evaluation in `check-eval`.** Baselines, feature work, tuning, early stopping, threshold choice, and error analysis use `train` and `val` only.
- Never re-split to get a better number. If the split is wrong, record why and make a new one. Results from the old split must not be compared to the new one.

## 2. Select models on validation or cross-validation

- Tune hyperparameters, choose features, pick thresholds, and stop early on `val`, or with cross-validation inside `train`+`val`.
- Cross-validation must respect the split strategy:
  - `group` → `GroupKFold` on the group column
  - `time` → rolling-origin / `TimeSeriesSplit` (with the same gap)
  - otherwise `StratifiedKFold` (classification) or `KFold`
- Prefer cross-validation for model selection when data is small (fewer than ~10,000 rows or ~200 positives). Report mean ± std across folds.

## 3. Report uncertainty

- Every headline metric gets a point estimate, a 95% bootstrap confidence interval, and `n` (and the number of positives for classification). Use [`eval_report.py`](../skills/check-eval/scripts/eval_report.py).
- Compare against the baseline with a **paired** bootstrap on the same rows.
- "Beats the baseline" means the delta's interval excludes zero in the better direction.
- An improvement whose interval includes zero is `CONDITIONAL` at best. Say so plainly.
- With fewer than 30 positives in the evaluation set, flag that the interval is too wide to support a decision.

## 4. Check slices, calibration, and the operating point

- **Slices:** evaluate key business segments and protected attributes. Flag any slice whose interval upper bound is below the overall point estimate (lower bound above it, for error metrics).
- **Calibration:** when probabilities drive decisions or are shown to users, report the Brier score and expected calibration error, and look at the reliability table.
- **Operating point:** pick the decision threshold on `val` with an explicit rule (cost matrix, review capacity, or target precision). Report precision, recall, and flagged rate at that threshold. Business impact (`demonstrate-value`) is computed from this operating point, never from AUPRC or ROC-AUC.

## 5. Evaluate on test once

- After the user accepts the model choice, `check-eval --final`:
  - produces test predictions (e.g. `train_tabular.py predict --split test`)
  - verifies `test_keys_sha256` against the manifest
  - reports the final metrics with intervals
- The final evaluation runs once per split. A second test evaluation is recorded as a `high` finding (test reuse), and the decision can be at most `CONDITIONAL`.

## 6. Task-specific rules

- **Forecasting:**
  - Rolling-origin backtest with several origins and a fixed horizon.
  - Scale-free errors (MASE, sMAPE).
  - Quantile loss or interval coverage for probabilistic forecasts.
  - Baselines: seasonal-naive, a statistical model, and a zero-shot time-series foundation model.
- **LLM fine-tuning and prompting:**
  - Check eval items for overlap with training data (contamination).
  - Use deterministic decoding (temperature 0) unless sampling is the point.
  - Keep the prompt template fixed across compared models.
  - Report the harness's standard errors.
- **Unsupervised:** fix the proxy metric before looking at results (stability, top-k precision under review, or a downstream metric).

## Predictions file

All scripts exchange predictions as CSV:

| Column | When |
|---|---|
| `row_key` | always — matches `split_assignments.csv` |
| `y_true` | always |
| `y_score` | binary — probability of the positive class |
| `score_<class>` | multiclass — one column per class |
| `y_pred` | regression; optional for classification |

Write them to `<out-dir>/predictions/<source>_<split>.csv`, e.g. `baseline_majority-class_val.csv`, `model_val.csv`, `model_test.csv`.
