---
name: feature-engineer
description: Explores data sources and engineers leakage-safe model features from files or databases. Use when asked to create features from raw tables/datasets, design joins and aggregations for a target label, improve model signal, or map business outcomes into trainable predictor sets. Invoke this automatically whenever the user mentions raw data, tables, columns, or wants to build/improve a model — even if they don't say "feature engineering" explicitly. Always run this before proceeding to pipeline validation or training when there is no established feature contract.
argument-hint: "[--data PATH|DATASET] [--db-url DSN] [--tables T1,T2,...] [--label-col COLUMN] [--entity-col COLUMN] [--timestamp-col COLUMN] [--outcome TEXT] [--task classification|regression|ranking|forecasting] [--out-dir DIR]"
---

# Feature Engineer

Explore source data and build reproducible, leakage-safe feature sets for the stated label and business outcome.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `--data PATH|DATASET` — file-based dataset or dataset identifier
- `--db-url DSN` — database connection string for SQL exploration
- `--tables T1,T2,...` — candidate source tables for feature generation
- `--label-col COLUMN` — target column
- `--entity-col COLUMN` — entity key for joining and split safety
- `--timestamp-col COLUMN` — event timestamp for point-in-time joins
- `--outcome TEXT` — business outcome statement
- `--task` — modeling task type
- `--out-dir DIR` — output directory for feature spec and implementation snippets

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Build the feature contract

Define:

- target label and business outcome
- prediction unit and prediction time
- allowed feature freshness window
- prohibited leakage sources

If this is missing, request the smallest clarification and continue.

### 2. Explore and profile feature sources

For file-based data:

- inspect schema, missingness, uniqueness, and basic distributions
- identify candidate numerical, categorical, text, and timestamp columns

For databases (`--db-url` + `--tables`):

- inspect schemas, primary/foreign key candidates, and joinability
- profile row counts, null rates, cardinality, and label coverage per table
- validate entity/time coverage before building joins

Use [references/db-feature-playbook.md](references/db-feature-playbook.md) for DB profiling and as-of join patterns.

### 3. Generate candidate features

Use patterns from [references/feature-patterns.md](references/feature-patterns.md):

- numeric transforms and clipping
- categorical handling (frequency, target-safe encoding, hashing)
- temporal features (recency, frequency, rolling stats)
- cross-table aggregations by entity/window
- text-derived and interaction features where relevant

Tie each feature family to an explicit modeling hypothesis.

### 4. Enforce leakage safety

Before finalizing features:

- verify `feature_time <= prediction_time`
- reject post-outcome columns
- ensure train/validation/test splits are entity-safe and time-consistent
- mark any risky feature as blocked with rationale

### 5. Produce implementation-ready outputs

Deliver:

- ranked feature inventory with rationale and risk
- SQL or Python snippets to materialize features
- data-quality checks required before training
- a minimal feature set for first baseline model

### 6. Hand off to pipeline validation

After feature plan is drafted:

- instruct running `check-data-pipeline` against the engineered feature pipeline
- include exact next commands for validation and training handoff

## Output format

```text
Feature Engineering Brief
=========================
Business outcome: <...>
Label: <...>
Entity: <...>
Prediction time: <...>

Source exploration:
1) <table/dataset> | rows=<...> | usable keys=<...> | notes=<...>

Candidate feature sets:
1) <feature family> | hypothesis=<...> | leakage risk=<low|medium|high>

Blocked features:
1) <feature> | reason=<leakage/unavailable/unstable>

Initial baseline feature set:
- <list>

Implementation snippets:
- <sql/python path or snippet summary>

Decision: GO | NO-GO | CONDITIONAL
Confidence: high|medium|low

Next commands:
- <pipeline validation command>
- <training command>
```

`GO`: feature contract complete, no blockers.
`CONDITIONAL`: feature brief is complete but one or more features carry medium/high leakage risk that should be tracked.
`NO-GO`: critical source information is missing or blockers prevent building a valid feature set.

### JSON artifact

Write `feature-engineer.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:
- `decision`: `GO` / `NO-GO` / `CONDITIONAL`
- `sources_explored`, `feature_sets`, `blocked_features`, `baseline_feature_set`
- `findings`: one entry per blocked feature (severity based on risk level) and any structural gaps

## Quick heuristics

- No timestamp column → default to random split; warn that temporal leakage cannot be verified
- High cardinality categoricals (> 500 unique values) → use frequency or hash encoding, not one-hot
- Entity column with duplicates in training data → group-aware split is mandatory or evaluation will be inflated
- Target-correlated ID column (e.g. `user_tier`, `account_type` that encodes the label) → flag as high leakage risk
- Rolling aggregations without `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` on ordered window → silently leaks future data
- Feature missingness > 30% in production but < 5% in training data → distribution shift blocker; check source query

## Stop conditions

Stop when:

- feature brief and implementation snippets are complete, or
- critical source information (keys, timestamps, label definition) is missing and explicitly requested.

## Additional resources

- [references/db-feature-playbook.md](references/db-feature-playbook.md) — DB exploration and as-of join templates
- [references/feature-patterns.md](references/feature-patterns.md) — reusable feature families and guardrails
