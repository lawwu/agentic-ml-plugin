# Lifecycle Gates

Use these gates in order. Each gate must record evidence and a pass/fail result. Gates that `select-approach`'s `lifecycle_map` marks as not applicable are recorded as `SKIPPED` with the reason.

| Gate | Objective | Pass criteria | Required evidence |
|---|---|---|---|
| 0. Approach selection | Choose the kind of ML/AI, cheapest first | Decision, output, and supervision are known; approach chosen; lifecycle map written | `select-approach.json` |
| 1. Target readiness | Confirm prediction goal, label, metric, and split | Label/business outcome is explicit; metric and threshold defined; split created and test set locked | `review-target.json`, `splits/split-manifest.json` |
| 2. Dataset quality | Detect hard data blockers before anything is computed on the data | No blocker-level leakage/schema/label/privacy issues; data contract saved | `check-dataset-quality.json`, `data-contract.json`, `training-profile.json` |
| 3. Baseline | Establish the performance floor | At least one baseline fit on `train` and scored on `val` with an interval; predictions saved | `build-baseline.json`, `predictions/baseline_*_val.csv` |
| 4. Experiment plan | Design hypothesis, candidates, HP search space, and compute budget | ≥ 1 simple candidate; budget fits constraints; success criteria defined relative to the gate 3 baseline; tuning on `val`/CV only | `plan-experiment.json` |
| 4b. Feature engineering (optional) | Leakage-safe features from raw data | Point-in-time correct features; blocked features recorded | `feature-engineer.json` |
| 5. Data pipeline integrity | Verify preprocessing and collation correctness | All required pipeline checks pass on a representative sample, including tabular leakage checks | `check-data-pipeline.json` |
| 6. Training stability | Ensure run health and recoverability | Pre-flight checks pass; no unresolved critical anomalies; provenance recorded; checkpoint progression observed | `train-model.json`, `babysit-training.json`, `provenance-train.json` |
| 7. Evaluation quality (validation) | Verify model quality on `val` against baseline and thresholds | Primary metric meets threshold; paired delta vs. baseline excludes zero; no flagged critical slices; operating point chosen | `check-eval.json`, `eval-metrics-val.json` |
| 8. Interpretability and bias | Ensure the model is explainable and bias is reviewed | No NO-GO blockers from bias or leakage audit; model card produced | `explain-model.json`, `MODEL_CARD.md` |
| 9. Deployment readiness | Ensure the model behaves the same when served, and will be monitored | Parity passes; budgets met; contract clean; monitoring and rollback plans written | `check-deployment-readiness.json`, `serving-check.json`, `monitoring-plan.md` |
| 10. Promotion decision | Decide whether to move forward | User accepted the model and threshold; evidence notebook verified; final test evaluation run once with a matching test hash; criteria met; user signed off | `check-eval.json` (final), `evidence-verify.txt`, `decision.md`, `run-summary.json` |

## Gate policy

- Any gate returning `NO-GO` halts the run immediately — do not execute subsequent gates.
- Allow retries for gate 6 (training) only, within budget and `--max-retries`; a `NO-GO` after all retries are exhausted halts the run.
- Gate 4b (`feature-engineer`) is optional: run it between gates 4 and 5 when the data is raw; otherwise record it as `SKIPPED` with the reason.
- A `CONDITIONAL` result passes the gate, but its caveats must be carried into the final summary's top risks.
- Gates 8 and 9 must complete before promotion; a `NO-GO` from either blocks gate 10.
- The test set is read only in gate 10, once. See [evaluation-protocol.md](../../../references/evaluation-protocol.md).
- Require explicit user approval to relax gate thresholds or continue past a `NO-GO`. Level and autonomy never relax gates.
