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

## xhard-churn — B2B SaaS Customer Churn

Source: `demo/scenarios/xhard-churn/`

```bash
uv run demo/scenarios/xhard-churn/generate_data.py
# → demo/scenarios/xhard-churn/data.csv  (~7,000–8,000 rows after survivorship filtering)
```

| Property | Value |
|---|---|
| Rows | ~7,000–8,000 (varies due to survivorship filtering) |
| Label column | `churned` |
| Label rate | ~20–27% churn (drifts across snapshots) |
| Entity column | `company_id` |
| Timestamp column | `snapshot_date` |
| Group column | `company_id` (required for group-aware split) |
| Task type | binary classification |
| Primary metric | `f1_macro` |
| Secondary metrics | `roc_auc`, disparate impact ratio per `region` and `company_size` |
| Required split | group-aware time-based (by `company_id` + `snapshot_date`) |

Key columns and their role in the benchmark:

| Column | Type | Pitfall |
|---|---|---|
| `support_tickets_open` | int | Composite leak — strong only when combined with `days_since_last_login` |
| `days_since_last_login` | int | Composite leak — strong only when combined with `support_tickets_open` |
| `next_quarter_pipeline_value` | float | Future-peeking — only known after prediction window closes |
| `snapshot_quarter` | int | Label drift marker — churn definition changes at quarter ≥ 4 |
| `discount_pct` | float | Simpson's paradox — positive overall correlation, negative within each `company_size` |
| `nps_score` | int | Feature staleness — refreshed annually (Q1 only), stale for 3 of 4 quarters |
| `region` | categorical | Protected proxy — encodes `company_size` confounding |
| `company_id` | string | Entity leak — must use group-aware split or same company leaks across train/test |

Benchmark notes:

- Use group-aware time-based split: train on earliest snapshots, test on latest; group by `company_id`
- `next_quarter_pipeline_value` must be dropped before training (post-outcome)
- Expect naive AutoML to show inflated `f1_macro` (~0.75+) due to entity leakage; correct split yields ~0.62–0.68
- Label drift (higher churn in Q4+) will cause underperformance on later-quarter test splits if not accounted for
