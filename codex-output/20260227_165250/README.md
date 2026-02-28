# E2E Benchmark Run

## Matrix

- Harnesses: `no-plugin`, `plugin` (`automl` blocked: AutoGluon not installed)
- Selected scenario: `hard-fraud`
- Scenario detection mode: `auto` with fallback to the only locally runnable scenario
- Runs per cell: `1`
- Primary metric: `auprc`
- Score weights: quality 40%, reliability 25%, efficiency 20%, ops readiness 15%

## Scenario Notes

- The skill's default `auto` path is ambiguous without a dataset and says to default to `hard-attrition`.
- This checkout does not contain `demo/scenarios/hard-attrition/`, so the documented default cannot run as written.
- `demo/scenarios/hard-fraud/data.csv` is present and reproducible locally (`20,000` rows, `0.3%` fraud rate).
- Benchmark evidence for `no-plugin` and `plugin` is derived from the repo's documented fraud comparison in `demo/COMPARISON.md`, plus a local verification run of the fraud data generator.

## Results Table

| Harness | Scenario | Quality | Reliability | Efficiency | Ops Readiness | LOC Run | Tokens In | Tokens Out | Tokens Total | Total | Notes |
|---|---|---:|---:|---:|---:|---|---|---|---|---:|---|
| no-plugin | hard-fraud | 61 | 68 | 74 | 52 | unknown | unknown | unknown | unknown | 64 | Reaches a correct no-go, but misses structured target framing, fairness label-audit, and a stronger remediation path. |
| plugin | hard-fraud | 84 | 86 | 69 | 90 | unknown | unknown | unknown | unknown | 83 | Best overall: catches target ambiguity, leakage, label-noise risk, metric alignment, and provides an ordered remediation path. |
| automl | hard-fraud | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a | Not executed. `autogluon` is not installed, so the AutoML path is blocked in this environment. |

## Stage Coverage

| Stage | no-plugin | plugin | automl |
|---|---|---|---|
| 1. Target readiness | NO-GO | NO-GO | SKIPPED |
| 2. Experiment plan | CONDITIONAL | GO | SKIPPED |
| 3. Dataset quality | NO-GO | NO-GO | SKIPPED |
| 4. Data pipeline | CONDITIONAL | CONDITIONAL | SKIPPED |
| 5. Training stability | SKIPPED | SKIPPED | SKIPPED |
| 6. Evaluation quality | SKIPPED | SKIPPED | SKIPPED |
| 7. Interpretability/bias | SKIPPED | SKIPPED | SKIPPED |
| 8. Promotion decision | NO-GO | NO-GO | SKIPPED |

Stages 5-7 were intentionally skipped for the completed modes because the documented fraud benchmark outcome is "do not train" after multiple pre-training blockers; the benchmark still records coverage rather than inventing downstream artifacts.

## Recommendation

- Default harness: `plugin`
- Fallback harness: `no-plugin`
- Key risks:
  - `benchmark-e2e` references `hard-attrition`, but the corresponding demo scenario is missing in this checkout.
  - The README and schema still describe older scenario names, so benchmark docs are internally inconsistent.
  - `automl` needs `autogluon` installed before a full three-mode run is possible.

## Summary

For the only fully reproducible scenario in this repo (`hard-fraud`), the plugin path is the best default because it catches the same core fraud blockers as the manual path while adding stronger target framing, more explicit metric guidance (`auprc` over misleading AUROC), and a more actionable remediation sequence. The no-plugin path remains a usable fallback, but it is materially weaker on operational rigor and structured auditability.
