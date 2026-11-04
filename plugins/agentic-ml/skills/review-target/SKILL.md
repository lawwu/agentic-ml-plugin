---
name: review-target
description: Reviews and validates machine learning target/label definitions against business outcomes before modeling. Use when asked to define or audit the prediction target, select metrics, set acceptance criteria, detect leakage risk, or choose split strategy for a new ML project. Invoke this automatically whenever a user mentions a business outcome, KPI, or states what they want to predict — before any data is loaded or features are engineered. Skipping target review is the single most common cause of wasted ML effort; always run this first on a new project.
argument-hint: "<business-outcome> [--data SOURCE] [--label-col COLUMN] [--entity-col COLUMN] [--timestamp-col COLUMN] [--horizon DURATION] [--task classification|regression|ranking|forecasting] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
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

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- `junior`: walk through each part of the prediction contract with an example row from their data.
- `staff`: focus on whether the target matches the business decision, and who owns the promotion threshold.

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

### 5. Choose the split strategy and lock the test set

Recommend the split policy from the task and data, following [../../references/evaluation-protocol.md](../../references/evaluation-protocol.md):

- `random`, `stratified`, `group`, or `time` — with the rationale tied to how the model will be used
- a gap between train and evaluation periods when labels mature after a delay
- minimum evaluation sample: at least ~30 positives (classification) or ~100 rows in each of `val` and `test`
- for forecasting: the horizon, the number of backtest origins, and the step between them

When `--data` is available, create the split once and lock the test set:

```bash
uv run "${CLAUDE_SKILL_DIR}/scripts/make_splits.py" --data <path> --label-col <col> \
  --strategy <random|stratified|group|time> [--id-col <col>] [--group-col <col>] [--time-col <col>] \
  [--gap 30d] --seed 42 --out-dir <out-dir>
```

This writes `<out-dir>/splits/split_assignments.csv` and `split-manifest.json` (with `test_keys_sha256`). Every later skill reads these files. Review the manifest's `warnings` — a test split with too few positives, or a random split on data with timestamps or repeated entities — and resolve them before `GO`.

Never create the split again later in the run to improve a number. `make_splits.py` refuses to overwrite an existing split with different settings; pass `--force` only when the split is genuinely wrong, and record why in the artifact.

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

### Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- an `exec` block that re-creates the split into `"$(mktemp -d)"` with the same arguments and prints the per-split counts, entity overlap, and `test_keys_sha256` — proof that the split reproduces from the data and seed
- for each `blocker`/`high` leakage risk: the computation that shows it (e.g. a crosstab of "column is filled in" against the label)

### JSON artifact

Write `review-target.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` / `NO-GO`
- `prediction_contract`: entity, prediction_time, target_event, horizon
- `leakage_risks`: one entry per risk found
- `primary_metric`, `promotion_threshold`, `split_strategy`
- `split_manifest_path` and `test_keys_sha256` when the split was created
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
