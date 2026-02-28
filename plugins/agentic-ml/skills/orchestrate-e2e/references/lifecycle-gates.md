# Lifecycle Gates

Use these gates in order. Each gate must record evidence and a pass/fail result.

| Gate | Objective | Pass criteria | Required evidence |
|---|---|---|---|
| 1. Target readiness | Confirm prediction goal and label definition | Label/business outcome is explicit; metric and split strategy defined | Target review summary (`review-target`) |
| 2. Experiment plan | Design hypothesis, candidates, HP search space, and compute budget | ≥ 1 baseline candidate; budget fits constraints; success criteria defined | Experiment plan (`plan-experiment`) |
| 3. Dataset quality | Detect hard data blockers before training | No blocker-level leakage/schema/label issues | Dataset audit report (`check-dataset-quality`) |
| 4. Data pipeline integrity | Verify preprocessing and collation correctness | All required pipeline checks pass on representative sample | Pipeline validation report (`check-data-pipeline`) |
| 5. Training stability | Ensure run health and recoverability | No unresolved critical anomalies; checkpoint progression observed | Monitoring timeline and run logs (`babysit-training`) |
| 6. Evaluation quality | Verify model quality against baseline and thresholds | Primary metric meets threshold; no critical regressions | Eval report and delta table (`check-eval`) |
| 7. Interpretability and bias | Ensure model is explainable and bias-free before promotion | No NO-GO blockers from bias or leakage audit; model card produced | Explainability report and model card (`explain-model`) |
| 8. Promotion decision | Decide whether to move forward | All mandatory gates passed and residual risk accepted | Final GO/NO-GO summary |

## Gate policy

- Any gate returning `NO-GO` halts the run immediately — do not execute subsequent gates.
- Allow retries for gate 5 only within budget and retry limits; a `NO-GO` after all retries are exhausted halts the run.
- Gate 7 (`explain-model`) must complete before any promotion; a `NO-GO` from gate 7 blocks gate 8.
- Require explicit user approval to relax gate thresholds or continue past a `NO-GO`.
