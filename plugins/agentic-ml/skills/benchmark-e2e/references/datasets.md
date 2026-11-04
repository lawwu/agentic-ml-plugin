# Dataset Catalog

Benchmark datasets for E2E runs. All datasets are generated locally from scripts in the repository's `demo/scenarios/` directory so results are reproducible across harnesses. Each generator writes `data.csv` next to itself by default (pass `--out PATH` to write elsewhere).

The generators are part of the repository checkout, not the installed plugin. Clone [lawwu/agentic-ml-plugin](https://github.com/lawwu/agentic-ml-plugin) to use them.

Two simpler scenarios are also available for demos and smoke tests (not used by `benchmark-e2e`):

- `easy` — premium-upgrade prediction; clean data, no leakage (1,200 rows)
- `medium` — telecom churn with a vague objective, a subtle temporal leak (`days_since_last_support_call`), and a mild protected-attribute gap (3,000 rows)

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
| Label rate | ~0.29% confirmed fraud (57 of 20,000 at the default seed) |
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
| `transaction_reviewed` | bool | Selection bias — only ~6% reviewed; unreviewed fraud is labeled `False` |
| `ip_country` | categorical | Geographic proxy / collection bias |
| `amount` | float | Bimodal (B2B + consumer); extreme outliers |

Benchmark notes:

- Use a fixed seed (`rng=42`) and time-based split at 80/10/10 by `transaction_timestamp`
- Expect naive AUROC ~0.97 that masks near-zero precision at low threshold

## hard-readmission — Hospital 30-Day Readmission

Source: `demo/scenarios/hard-readmission/`

```bash
uv run demo/scenarios/hard-readmission/generate_data.py
# → demo/scenarios/hard-readmission/data.csv  (4,000 rows)
```

| Property | Value |
|---|---|
| Rows | 4,000 |
| Label column | `readmitted_30d` |
| Label rate | ~11% readmitted |
| Entity column | `patient_id` |
| Timestamp column | none (use stratified split) |
| Task type | binary classification |
| Primary metric | `auprc` |
| Secondary metrics | `roc_auc`, disparate impact ratio per protected attribute |
| Protected attributes | `race`, `age`, `gender` |

Key columns and their role in the benchmark:

| Column | Type | Pitfall |
|---|---|---|
| `days_until_readmission` | float (null unless readmitted) | Target echo — non-null only for positives |
| `discharge_notes_readmission_risk` | float | Proxy leakage — clinician's own outcome judgment |
| `died_before_30d` | bool | Censoring — deceased patients labeled `False`; must be excluded |
| `discharge_to` | categorical | Prediction-time ambiguity — known only at discharge |
| `insurance_type` | categorical | Proxy — generated conditional on `race` |
| `attending_physician_id` | categorical (60 values) | High-cardinality physician proxy |

Benchmark notes:

- Use stratified split (stratify on `readmitted_30d`) with fixed seed
- Expect `days_until_readmission` to be flagged as a blocker by `check-dataset-quality` and to dominate importance if it reaches training
- Expect the `insurance_type` → `race` proxy to surface in the `explain-model` bias audit

## xhard-churn — B2B SaaS Customer Churn

Source: `demo/scenarios/xhard-churn/`

```bash
uv run demo/scenarios/xhard-churn/generate_data.py
# → demo/scenarios/xhard-churn/data.csv  (~6,400 rows after survivorship filtering)
```

| Property | Value |
|---|---|
| Rows | ~6,400 (6,366 at the default seed; varies with survivorship filtering) |
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
