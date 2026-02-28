# Scenarios

Use these definitions to classify exactly one scenario per benchmark run.

## hard-fraud

E-commerce fraud detection with compounding pitfalls that naive approaches consistently miss.

Representative pitfalls:

- **Target echo**: `chargeback_initiated_days_ago` is only non-null for fraud cases — perfect label leak
- **Selection bias**: only 8% of transactions were manually reviewed; unreviewed non-fraud contains ~5% undetected fraud (mislabeled negatives)
- **Feedback loop**: `previous_model_risk_score` is output of the prior model — model learns to agree with its predecessor, not reality
- **Extreme imbalance**: 0.3% fraud rate — AUROC is meaningless; requires AUPRC or precision@k
- **Near-perfect feature leak**: `device_fingerprint_age_hours` < 2h is almost always fraud; value range reveals the label
- **Concept drift**: fraud patterns shift monthly; random split leaks future signatures into training
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

## hard-attrition

Employee attrition prediction with label ambiguity, survivorship bias, and protected attribute pitfalls.

Representative pitfalls:

- **Target echo**: `exit_survey_score` is 100% null for non-leavers — perfect oracle of the label
- **Label ambiguity**: `left_company` conflates voluntary resignation, involuntary termination, and retirement — fundamentally different predictors
- **Survivorship bias**: employees who left >2 years ago are excluded; long-tenured employees are overrepresented, inflating tenure coefficients
- **Endogenous feature**: `performance_score_last_review` for managed-out employees reflects the termination decision, not prior performance
- **Protected attribute proxies**: `salary` encodes gender/ethnicity pay gaps; `commute_distance_km` proxies zip/neighborhood
- **High-cardinality manager proxy**: `manager_id` (80 managers) encodes culture/quality, not individual employee risk
- **Multiple protected attributes**: gender (F attrition 24% vs M 18%), ethnicity, age (55+)

Typical goal: define a precise, bias-safe target before modeling; surface pay discrimination before promotion.

Dataset: `demo/scenarios/hard-attrition/data.csv` (6,000 rows, generated)

```bash
uv run demo/scenarios/hard-attrition/generate_data.py
```

Benchmark configuration:

- Task type: binary classification
- Primary metric: `f1` (macro, to surface class imbalance)
- Label column: `left_company`
- Entity column: `employee_id`
- Protected attributes: `gender`, `ethnicity`, `age`

Why it differentiates: Without `review-target`, agents miss the label ambiguity and build a mixed voluntary/involuntary model. Without `explain-model`, the salary proxy discrimination is never surfaced. AutoML produces a model that encodes pay discrimination as signal.

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

Dataset: `demo/scenarios/xhard-churn/data.csv` (~7,000–8,000 rows after survivorship filtering, generated)

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
   - `left_company` label column or `exit_survey_score` present → `hard-attrition`

2) If no signature matches, default to `hard-attrition` and explain why.

3) Output exactly one label: `hard-fraud`, `hard-attrition`, or `xhard-churn`.
