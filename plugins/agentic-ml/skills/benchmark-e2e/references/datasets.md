# Dataset Catalog

Benchmark datasets for E2E runs. Both datasets are generated locally from scripts in `demo/scenarios/` so results are reproducible across harnesses.

## hard-fraud — E-commerce Fraud Detection

Source: `demo/scenarios/hard-fraud/`

```bash
uv run demo/scenarios/hard-fraud/generate_data.py
# → demo/scenarios/hard-fraud/data.csv  (20,000 rows)
```

| Property | Value |
|---|---|
| Rows | 20,000 |
| Label column | `is_fraud` |
| Label rate | ~0.3% fraud |
| Entity column | `transaction_id` |
| Timestamp column | `transaction_timestamp` |
| Task type | binary classification |
| Primary metric | `auprc` |
| Secondary metrics | `precision_at_k`, `roc_auc` (for comparison only) |
| Required split | time-based (by `transaction_timestamp`) |

Key columns and their role in the benchmark:

| Column | Type | Pitfall |
|---|---|---|
| `chargeback_initiated_days_ago` | float (mostly null) | Target echo — null for all non-fraud |
| `device_fingerprint_age_hours` | float | Near-perfect leak — <2h almost always fraud |
| `previous_model_risk_score` | float | Feedback loop — prior model output |
| `transaction_reviewed` | bool | Selection bias — only 8% reviewed |
| `ip_country` | categorical | Geographic proxy / collection bias |
| `amount` | float | Bimodal (B2B + consumer); extreme outliers |

Benchmark notes:

- Use a fixed seed (`rng=42`) and time-based split at 80/10/10 by `transaction_timestamp`
- Expect naive AUROC ~0.97 that masks near-zero precision at low threshold

## hard-attrition — Employee Attrition Prediction

Source: `demo/scenarios/hard-attrition/`

```bash
uv run demo/scenarios/hard-attrition/generate_data.py
# → demo/scenarios/hard-attrition/data.csv  (6,000 rows)
```

| Property | Value |
|---|---|
| Rows | 6,000 |
| Label column | `left_company` |
| Label rate | ~20% attrition |
| Entity column | `employee_id` |
| Timestamp column | none (use stratified split) |
| Task type | binary classification |
| Primary metric | `f1` (macro) |
| Secondary metrics | `roc_auc`, disparate impact ratio per protected attribute |
| Protected attributes | `gender`, `ethnicity`, `age` |

Key columns and their role in the benchmark:

| Column | Type | Pitfall |
|---|---|---|
| `exit_survey_score` | float (null for stayers) | Target echo — 100% null for non-leavers |
| `performance_score_last_review` | int | Endogenous — reflects termination decision |
| `salary` | float | Proxy — encodes gender/ethnicity pay gaps |
| `manager_id` | categorical (80 values) | High-cardinality manager proxy |
| `commute_distance_km` | float | Proxy — correlates with zip/SES |

Benchmark notes:

- Use stratified split (stratify on `left_company`) with fixed seed
- Expect `exit_survey_score` to appear as top feature with near-100% importance — automatic blocker in `explain-model`
- Disparate impact on `gender` and `ethnicity` expected to fail threshold (<0.8)
