# tried — What else was tried, and how many looks were taken?

The best of many attempts looks better than it is, and a reviewer sees only the winner. This page shows the paths not taken and how many times the result was looked at.

**Claim letter:** T

## Sources

- `plan-experiment.json`: `hypothesis`, `candidates` (`rank`, `model_family`, `rationale`), `success_criteria`, `total_budget_gpu_hours`, `experiment_order`. Required.
- `select-approach.json`: `recommended_approach`, `ruled_out` (`approach`, `reason`), `what_would_change_this`. When present.
- `train-model.json`: `terminal_state`, `sweep` (`trials`, `objective`, `best_value`), `preflight`, `training_duration_seconds`. When present.
- `check-eval.json` → `protocol/test_evaluations`. When present.

## Headline

Before training: "The plan is to try <n> candidates, starting with <first>." After training: "<Chosen family> was picked from <n> candidates after <trials> tuning runs."

## Picture

A path from left to right in three steps, each a column of labelled boxes:

1. **Ruled out before starting:** each `ruled_out` approach with its reason in a few words.
2. **Planned:** each candidate, in `experiment_order`.
3. **Run:** the candidate that was trained, with its tuning-run count and how it ended.

Planned candidates that were never run stay visible and are marked "not run". Bind the chart to `plan-experiment.json#/candidates`.

## Facts to bind

- `hypothesis`, in full.
- `success_criteria/primary` and `success_criteria/failure_trigger`: what was agreed to count as success and as a stop.
- `sweep/trials`, and what the tuning was scored on (`sweep/objective`).
- `protocol/test_evaluations`.
- Planned budget (`total_budget_gpu_hours`).
- Each `preflight` check whose result is not `pass`.

## Only you can judge

- Is an obvious approach missing from the first two columns?
- Were the success and stop rules written before the results were seen?
- Is the number of tries small enough that the winner is not luck?
- Does anything in `what_would_change_this` now apply?

## Distrust this if

- `sweep/objective` is neither `val` nor `cv`.
- `protocol/test_evaluations` is above one.
- There were many tuning runs and the gain's interval on the baseline page barely clears zero.
- A planned candidate was not run and nothing says why.
- A `preflight` check has result `fail` or `skipped`.
- `terminal_state` is not `SUCCEEDED` or `EARLY_STOPPED`.
- `ruled_out` is empty: no alternative was considered on record.

## Leave out

Hyperparameter values and training curves.
