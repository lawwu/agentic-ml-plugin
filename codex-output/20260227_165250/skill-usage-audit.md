# Skill Usage Audit

| Harness | Scenario | Expected Skills | Actual Skills | Missing Critical Skills | Notes |
|---|---|---|---|---|---|
| no-plugin | hard-fraud | none | none | none | Matches the benchmark contract. Any skill invocation here would be an audit violation. |
| plugin | hard-fraud | `review-target`, `plan-experiment`, `check-dataset-quality`, `check-data-pipeline`, `babysit-training`, `check-eval`, `explain-model` | benchmark evidence derived from `demo/COMPARISON.md`; exact per-skill artifacts not present in repo | `check-data-pipeline`, `babysit-training`, `check-eval`, `explain-model` (not individually evidenced) | The repo contains a summarized plugin vs no-plugin comparison, not a full per-skill execution trace for the fraud scenario. |
| automl | hard-fraud | none | none | n/a | Mode not executed because `autogluon` is not installed. No skill audit violation. |
