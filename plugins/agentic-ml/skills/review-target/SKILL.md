---
name: review-target
description: Reviews and validates machine learning target/label definitions against business outcomes before modeling. Use when asked to define or audit the prediction target, select metrics, set acceptance criteria, detect leakage risk, or choose split strategy for a new ML project. Invoke this automatically whenever a user mentions a business outcome, KPI, or states what they want to predict — before any data is loaded or features are engineered. Skipping target review is the single most common cause of wasted ML effort; always run this first on a new project.
argument-hint: "<business-outcome> [--data SOURCE] [--label-col COLUMN] [--entity-col COLUMN] [--timestamp-col COLUMN] [--horizon DURATION] [--task classification|regression|ranking|forecasting]"
---

# Review Target

Validate that the target definition is measurable, leakage-safe, and aligned with business outcomes.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<business-outcome>` — plain-language statement of the decision/outcome to optimize
- `--data SOURCE` — dataset path, dataset ID, or DB table/query
- `--label-col` — existing label column (if already materialized)
- `--entity-col` — entity key (user, account, order, device, etc.)
- `--timestamp-col` — event time used for point-in-time validity
- `--horizon` — prediction window (for example `7d`, `30d`)
- `--task` — modeling task family

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Translate business outcome into a prediction contract

Define:

- predicted unit (`who/what`)
- prediction timestamp (`when`)
- target event (`what outcome`)
- decision horizon (`how far ahead`)

If this cannot be stated unambiguously, return `NO-GO` for modeling.

### 2. Define target label logic

Use [references/target-spec-template.md](references/target-spec-template.md) and specify:

- precise label formula
- positive/negative class rules (or regression target transformation)
- allowed data sources for label generation
- exclusions and edge-case handling

### 3. Run leakage and observability checks

Validate that every feature candidate can be known at prediction time:

- no post-outcome signals in features
- no direct target echoes in text/categorical fields
- no entity overlap leakage across train/validation/test

Flag each risk with severity and concrete mitigation.

### 4. Select metric and acceptance criteria

Use [references/metric-playbook.md](references/metric-playbook.md) to select:

- primary model selection metric
- secondary guardrail metrics
- minimum threshold for promotion
- decision-threshold policy (for probabilistic outputs)

### 5. Choose split strategy

Recommend split policy based on task/data:

- random, stratified, group-aware, or time-based split
- rationale tied to deployment scenario
- minimum validation sample requirements

### 6. Produce a target review brief

Deliver a concise brief with:

- approved target definition
- leakage findings and mitigations
- metric/split recommendations
- explicit `GO` or `NO-GO` to proceed with training

## Output format

```text
Target Review Brief
===================
Business outcome: <...>
Prediction contract: <entity, timestamp, horizon, event>
Task type: <...>

Target definition:
- Label formula: <...>
- Inclusion/exclusion rules: <...>

Leakage review:
1) <risk> | severity=<...> | mitigation=<...>

Evaluation policy:
- Primary metric: <...>
- Guardrails: <...>
- Promotion threshold: <...>

Split strategy:
- Method: <...>
- Rationale: <...>

Decision: GO|NO-GO
Confidence: high|medium|low
```

### JSON artifact

Write `review-target.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` / `NO-GO`
- `prediction_contract`: entity, prediction_time, target_event, horizon
- `leakage_risks`: one entry per risk found
- `primary_metric`, `promotion_threshold`, `split_strategy`
- `findings`: one entry per leakage risk or blocker (severity mapped from the leakage review)

## Quick heuristics

- Business outcome defined only as "improve X" without a measurable threshold → NO-GO; ask for a concrete decision criterion
- Outcome event happens post-prediction by design (e.g. "will churn in next 30 days") → ensure horizon is explicit and features are windowed accordingly
- Label derived from the same system as features (e.g. both from same `events` table) → verify there is no circular dependency
- Outcome rate < 1% → binary cross-entropy loss will underweight positives; note need for weighted loss or resampling
- No entity key specified but multiple rows per entity exist → entity-level leakage is undetectable; ask for the key
- Very high baseline accuracy (> 95%) achievable with one column → that column is either the target itself or a strong proxy; verify leakage before trusting it

## Stop conditions

Stop when:

- target brief is complete with a clear decision, or
- required business-policy input is missing and cannot be inferred safely.

## Additional resources

- [references/target-spec-template.md](references/target-spec-template.md) — target definition template
- [references/metric-playbook.md](references/metric-playbook.md) — metric/threshold guidance by task and outcome
