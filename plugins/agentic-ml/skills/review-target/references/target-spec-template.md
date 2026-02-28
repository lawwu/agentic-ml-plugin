# Target Spec Template

Use this template to define labels before feature engineering or training.

## 1) Prediction contract

- Entity: `<entity id>`
- Prediction timestamp: `<as-of time>`
- Horizon: `<duration>`
- Outcome event: `<event definition>`

## 2) Label logic

- Type: `classification | regression | ranking | forecasting`
- Label formula (plain language):
- Label formula (pseudo-SQL or code):
- Positive class definition (if classification):
- Missing/unknown label handling:

## 3) Point-in-time policy

- Allowed feature data cutoff: `feature_time <= prediction_time`
- Forbidden sources (post-outcome, manual review labels, future aggregates):
- Backfill policy:

## 4) Data exclusions

- Entities to exclude:
- Time ranges to exclude:
- Known data quality exclusions:

## 5) Acceptance policy

- Primary metric:
- Minimum threshold:
- Guardrail metrics:
- Fallback baseline:
