# Skill Matrix

Required skill usage per benchmark cell. All modes must attempt all 9 lifecycle stages. The skill chain is identical for `hard-fraud`, `hard-attrition`, and `xhard-churn`.

## plugin mode

Invoke each skill individually in stage order. Do not use `orchestrate-e2e` as a wrapper — invoke sub-skills directly so the benchmark always covers all 9 stages regardless of individual gate decisions.

| Stage | Skill |
|---|---|
| 1. Target readiness | `review-target` |
| 2. Experiment plan | `plan-experiment` |
| 3. Non-ML baseline | `build-baseline` |
| 4. Dataset quality | `check-dataset-quality` |
| 5. Data pipeline | `check-data-pipeline` |
| 6. Training stability | `train-model` (delegates to `babysit-training` + `check-failed-run` on failure) |
| 7. Evaluation quality | `check-eval` |
| 8. Interpretability/bias | `explain-model` |
| 9. Promotion decision | record final GO/NO-GO from stage results |

Any stage that is skipped (e.g., no checkpoint produced) must be recorded as `SKIPPED` with reason.

## no-plugin mode

- Expected skills: none (zero skill invocations; any skill call is an audit violation)
- Execute all 9 stages manually

## automl mode

- Expected skills: none (zero skill invocations; AutoGluon package only)
- Map AutoGluon outputs to all 9 stages per [modes.md](modes.md)

## Audit violations

For `no-plugin` and `automl`, any skill invocation is an audit violation. Report as `extra` in the skill usage audit table.

For `plugin`, record expected vs. actually used skills per stage. Missing skills or extra skills are both audit findings.
