# Scenarios

Use these definitions to classify exactly one scenario per benchmark run.

## hard-fraud

E-commerce fraud detection with compounding pitfalls that naive approaches consistently miss.

Representative pitfalls:

- **Target echo**: `chargeback_initiated_days_ago` is only non-null for fraud cases — perfect label leak
- **Selection bias**: only ~6% of transactions were manually reviewed; true fraud that was never reviewed is labeled `False` (3 of 60 fraud cases at the default seed) — the label is "confirmed fraud", not "fraud"
- **Feedback loop**: `previous_model_risk_score` is output of the prior model — model learns to agree with its predecessor, not reality
- **Extreme imbalance**: 0.3% fraud rate — AUROC is meaningless; requires AUPRC or precision@k
- **Near-perfect feature leak**: `device_fingerprint_age_hours` < 2h is almost always fraud; value range reveals the label
- **Time-based evaluation**: the model scores future transactions, so evaluate forward in time by `transaction_timestamp` (the generator does not simulate drift; a time split is still the correct protocol)
- **Geographic proxy**: `ip_country` reflects data collection bias, not causal fraud signal

Typical goal: maximize precision@k and AUPRC without leakage; enforce time-based split.

Dataset: `demo/scenarios/hard-fraud/data.csv` (20,000 rows, generated)

```bash
uv run demo/scenarios/hard-fraud/generate_data.py
```

Benchmark configuration:

- Task type: binary classification
- Primary metric: `auprc` (not `roc_auc` — naive approaches will use AUROC and miss the imbalance problem)
- Label column: `is_fraud`
- Entity column: `transaction_id`
- Timestamp column: `transaction_timestamp` (required for time-based split)

Why it differentiates: AutoML and no-plugin approaches typically report 99.7% accuracy or misleading AUROC scores. Skills (`review-target`, `check-dataset-quality`, `explain-model`) catch the metric error, target echo, and concept drift requirement.

## hard-readmission

Hospital 30-day readmission prediction with post-outcome leakage, censoring, and protected-attribute proxies.

Representative pitfalls:

- **Target echo**: `days_until_readmission` is non-null only for readmitted patients — perfect label leak
- **Proxy leakage**: `discharge_notes_readmission_risk` is the clinician's own readmission-risk judgment at discharge — it partially encodes the outcome
- **Censoring**: `died_before_30d` patients are labeled `False` but could not have been readmitted — they must be excluded, not treated as negatives
- **Prediction-time ambiguity**: `discharge_to` is only known at discharge; whether it is a valid feature depends on whether the prediction is made at admission or at discharge (and `Hospice` almost never readmits)
- **Label ambiguity**: planned readmissions (e.g. the next chemo cycle) and unplanned readmissions (complications) are conflated in one 30-day label
- **Protected attribute proxies**: `insurance_type` is generated conditional on `race` and acts as a race/SES proxy
- **High-cardinality physician proxy**: `attending_physician_id` (60 values) encodes physician-level variability, not patient risk
- **Protected attributes with real outcome gaps**: `race` (readmission is generated with a race effect), `age`, `gender`

Typical goal: pin down prediction time and the label definition (exclude censored patients, separate planned readmissions) before modeling; surface proxy bias before promotion.

Dataset: `demo/scenarios/hard-readmission/data.csv` (4,000 rows, generated)

```bash
uv run demo/scenarios/hard-readmission/generate_data.py
```

Benchmark configuration:

- Task type: binary classification
- Primary metric: `auprc` (positive rate ~11%)
- Label column: `readmitted_30d`
- Entity column: `patient_id`
- Timestamp column: none (use a stratified split on `readmitted_30d`)
- Protected attributes: `race`, `age`, `gender`

Why it differentiates: Without `review-target`, agents treat deceased patients as negatives and never ask when the prediction is made. Without `check-dataset-quality`, `days_until_readmission` goes straight into training. Without `explain-model`, the `insurance_type` race proxy is never surfaced.

## xhard-churn

B2B SaaS customer churn prediction with composite, multi-step pitfalls — no single-column leakage.

Representative pitfalls:

- **Composite leak**: `support_tickets_open` + `days_since_last_login` together predict churn near-perfectly via an interaction term, but neither alone provides strong signal — a naive feature-importance check misses it
- **Entity-level temporal leakage**: same `company_id` appears across multiple quarterly snapshots; random splits mix the same company into train and test (requires group-aware time-based split by `company_id` + `snapshot_date`)
- **Survivorship bias**: companies that churned early are absent from later snapshots — naive random splits mix temporal cohorts and underestimate true churn rate
- **Label definition drift**: `churned` definition changes at `snapshot_quarter` ≥ 4 (from "no renewal" to "no renewal OR downgrade >50%"), inflating the churn rate and invalidating cross-period comparison
- **Future-peeking feature**: `next_quarter_pipeline_value` is only known after the prediction window closes (post-outcome); appears predictive in the full dataset but is unavailable at inference time
- **Simpson's paradox**: `discount_pct` correlates positively with churn overall (+0.07), but negatively within each `company_size` segment — naive models learn the wrong direction; only segment-aware analysis reveals the true causal direction
- **Protected proxy**: `region` is a proxy for `company_size` which correlates with churn; a bias audit should flag regional disparate impact traceable to size confounding
- **Feature staleness**: `nps_score` is updated only annually (Q1), stale for 3 of 4 quarters; models treating it as current signal introduce systematic error

Typical goal: build a group-time-split churn model using `f1_macro`; surface composite interactions, label drift, and future-peeking features before training.

Dataset: `demo/scenarios/xhard-churn/data.csv` (~6,400 rows after survivorship filtering — 6,366 at the default seed; generated)

Known gap: at the default seed the composite leak is weak (univariate and pairwise AUC ≈ 0.54) and the Simpson's-paradox reversal does not hold in the large-company segment. Treat those two pitfalls as aspirational until the generator is reworked.

```bash
uv run demo/scenarios/xhard-churn/generate_data.py
```

Benchmark configuration:

- Task type: binary classification
- Primary metric: `f1_macro` (balanced across churn/retain classes and company segments)
- Label column: `churned`
- Entity column: `company_id`
- Timestamp column: `snapshot_date` (required for group-aware time-based split)
- Group column: `company_id` (must be used with timestamp for proper split)

Auto-detection rule: `churned` label column AND `company_id` AND `snapshot_date` all present → `xhard-churn`.

Why it differentiates: AutoML and no-plugin modes miss the composite interaction, apply random splits leaking entity-level data, and never detect label drift. Plugin mode (`review-target` + `check-dataset-quality` + `explain-model`) catches all 8 pitfalls through structured checks.

## Scenario setup checklist

For the selected scenario, document before benchmarking:

- dataset path and generation command
- label column, task type, and primary metric
- entity and timestamp columns
- known pitfalls (from the lists above) — record which ones each mode catches

## Automatic scenario identification (choose one)

When `--scenario auto` is used, classify with this protocol:

1) Inspect the dataset for the known scenario signatures (check in priority order):
   - `churned` label column AND `company_id` AND `snapshot_date` present → `xhard-churn`
   - `is_fraud` label column or `transaction_timestamp` present → `hard-fraud`
   - `readmitted_30d` label column or `days_until_readmission` present → `hard-readmission`

2) If no signature matches, stop and ask the user which scenario to run (or to pass `--dataset` with `--label-col`) — do not guess.

3) Output exactly one label: `hard-fraud`, `hard-readmission`, or `xhard-churn`.
