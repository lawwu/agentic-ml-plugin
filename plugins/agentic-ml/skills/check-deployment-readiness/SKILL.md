---
name: check-deployment-readiness
description: Checks that a model is ready to serve before promotion. Packages it with an input/output signature, re-loads it in a fresh process and compares its predictions to training-time predictions (training/serving skew), measures latency, throughput, and memory against budgets, validates inference inputs against the data contract, and writes a monitoring plan (drift, delayed-label performance, alerts, retraining) and a rollout and rollback plan. Use after evaluation and explainability, before a promotion or deployment decision, or when asked "is this ready for production?", "how do we monitor this model?", or "what's the rollout plan?".
argument-hint: "<model-path> [--data PATH] [--ref-pred PRED.csv] [--contract data-contract.json] [--latency-budget-ms N] [--memory-budget-mb N] [--serving batch|online] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Check Deployment Readiness

Answer one question before promotion: will this model behave in production the way it did offline, and will anyone notice if it stops?

This skill never deploys, registers, or routes traffic. It produces evidence and plans; those actions need approval.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<model-path>` — the trained model (e.g. `<out-dir>/model.joblib` from `train_tabular.py`, an HF checkpoint, or a model ID for hosted LLMs)
- `--data PATH` — raw data used to rebuild inference inputs
- `--ref-pred PRED.csv` — training-time predictions to compare against (default: `<out-dir>/predictions/model_val.csv`)
- `--contract` — data contract (default: `<out-dir>/data-contract.json`); the drift baseline `training-profile.json` is read from the same directory
- `--latency-budget-ms N` — per-request p95 latency budget for online serving
- `--memory-budget-mb N` — memory budget for the serving process
- `--serving batch|online` — how predictions will be served (default: ask, or infer from `review-target.json`)
- `--out-dir DIR` — output directory (default: `./`)
- `--run-id ID` — run ID shared across orchestrated skills
- `--level` — `junior`, `senior`, or `staff`

Target: `$ARGUMENTS`

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- `junior`: explain training/serving skew and why the monitoring plan needs owners.
- `staff`: emphasize ownership, on-call, cost of running, and the rollback decision rule.

## Your responsibilities

### 1. Package the model with a signature

- Copy or reference the model in `<out-dir>/model/`.
- Write `<out-dir>/model/signature.json`:
  - inputs: column names, order, and dtype kinds from `data-contract.json`
  - output: score or class, plus the decision threshold from `check-eval`'s operating point
  - version: git SHA and data sha256 from the provenance record
- If the project uses MLflow, offer to log the model with its signature. Registering a model version is `needs-approval`.

### 2. Check training/serving parity and performance

Re-load the model in a **fresh process** and score `val` rows rebuilt from raw data. Never use `test`.

```bash
uv run "${CLAUDE_SKILL_DIR}/scripts/serving_check.py" --model <model> --data <path> \
  --ref-pred <out-dir>/predictions/model_val.csv --label-col <col> --key-col <row-key-col> \
  --contract <out-dir>/data-contract.json --latency-budget-ms <N> --out <out-dir>/serving-check.json
```

- **Parity:** predictions must match the training-time predictions within tolerance (default `1e-6`). A mismatch means the serving path builds features differently from training. This is a blocker.
- **Latency and throughput:** single-row p50/p95/p99 and batch rows per second, against the budget for the serving mode.
- **Footprint:** model size and peak memory, against `--memory-budget-mb`.
- **Contract:** inference inputs pass `data-contract.json` (columns, order, types).

Notes:

- Add `--with lightgbm` (or `xgboost`, `catboost`) when the model needs it to load.
- Input data is CSV.
- Set `OMP_NUM_THREADS` to match the serving configuration before measuring latency; tree models can be several times slower per row with default threading on a busy machine. The output records the setting.

For HF checkpoints or LLM approaches, replace the script with an equivalent check: replay a fixed set of `val` inputs through the serving path with deterministic decoding and compare outputs. Measure latency and cost per request. Record the pinned model and prompt versions. Confirm data egress is allowed for hosted models.

### 3. Confirm the drift baseline

Check that `training-profile.json` exists (from `check-dataset-quality`). If not, create it with `check-dataset-quality`'s `data_contract.py build` on the `train` split. Production inputs are compared against this baseline.

### 4. Write the monitoring plan

Write `<out-dir>/monitoring-plan.md` with:

| Signal | What to compute | Alert threshold | Owner |
|---|---|---|---|
| Input contract | `data_contract.py validate` on each production batch | any blocker violation | |
| Feature drift | PSI per feature vs. `training-profile.json` | > 0.25 major, 0.1–0.25 watch | |
| Prediction drift | PSI of the score distribution vs. `val` | > 0.25 | |
| Performance | primary metric with CI on labels as they mature (label delay from `review-target`'s horizon) | CI upper bound below the promotion threshold | |
| Operations | latency p95, error rate, throughput | above budget | |
| Staleness | model age; data recency | older than the retraining cadence | |

Then add:

- the retraining trigger and cadence
- who is paged and who decides on rollback

Leave owners blank rather than inventing names; list them as open items.

### 5. Write the rollout and rollback plan

In the same file:

- **Rollout:** shadow (score without acting, compare to the current process), then canary (a small traffic share for a fixed period with explicit success criteria), then full.
- **Rollback:** the criteria (e.g. a canary metric CI below the current model's, a contract blocker, latency over budget) and the mechanism (the previous model version or the rule baseline from `build-baseline`).

### 6. Decide

- `GO`: parity passes, budgets are met (or none apply), contract checks are clean, and the monitoring and rollback plans are written.
- `CONDITIONAL`: budgets were not provided, monitoring owners are missing, or there are non-blocking contract issues — list each.
- `NO-GO`: parity fails (training/serving skew), a budget is exceeded, inference inputs violate the contract, or the model cannot be loaded outside the training process.

## Output format

```text
Deployment Readiness
====================
Model: <path> (version <git sha> / data <sha256 prefix>)
Serving: batch | online

Parity:      PASS|FAIL  n=<rows>  max |diff|=<value>
Latency:     p50=<ms> p95=<ms> p99=<ms>  budget=<ms>  PASS|FAIL|n/a
Throughput:  <rows/s> (batch of <N>)
Footprint:   model=<MB>  peak RSS=<MB>  budget=<MB>  PASS|FAIL|n/a
Contract:    <violations> violations (<blockers> blockers)
Drift baseline: <path>

Monitoring plan: <out-dir>/monitoring-plan.md (<n> open owner items)
Rollout: shadow → canary (<share>, <duration>) → full
Rollback: <criteria>

Decision: GO | CONDITIONAL | NO-GO
Confidence: high|medium|low
```

### Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- parity and contract: `exec` `serving_check.py` with `--out "$(mktemp)"` and print only the parity and contract fields. Latency changes from run to run, so record it in a note with the measured values and the `OMP_NUM_THREADS` setting
- the signature: an `exec` block printing the input columns and the decision threshold from `signature.json`

### JSON artifact

Write `check-deployment-readiness.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`, `model_path`, `package_format`, `signature_path`
- `parity`, `latency`, `throughput_rows_per_s`, `model_size_mb`, `peak_rss_mb`, `contract_check`
- `drift_baseline_path`, `monitoring_plan_path`, `rollout`
- `findings`: parity failure (`blocker`), budget violations (`high`), contract issues (by severity), missing owners (`medium`)

## Fix policy

Apply without approval:

- Loading the model and scoring `val` rows in a separate process
- Writing the signature, the serving-check output, and the plans

Require user approval before:

- Registering a model version, deploying, or changing traffic
- Calling hosted model or embedding APIs with real data

## Quick heuristics

- Parity fails by a small constant → a scaler or imputer was refit at serving time; serve the fitted pipeline, not re-built transforms
- Parity fails on a few rows only → unseen categories or nulls handled differently at serving time
- p95 latency far above p50 → cold starts or garbage collection; warm up and measure again before blaming the model
- No labels until months after prediction → monitor input and prediction drift as leading indicators, and say so in the plan
- No rule baseline to roll back to → the rollback target is the previous model; make sure it is still loadable

## Stop conditions

Stop when:

- the readiness report, `monitoring-plan.md`, and the JSON artifact are written, or
- the model cannot be loaded, or required inputs (data, reference predictions) are missing — report exactly what is needed.

## Additional resources

- [scripts/serving_check.py](scripts/serving_check.py) — fresh-process parity, latency, throughput, memory, and contract check
- [../check-dataset-quality/scripts/data_contract.py](../check-dataset-quality/scripts/data_contract.py) — data contract and drift baseline
- [../../references/evaluation-protocol.md](../../references/evaluation-protocol.md) — evaluation rules, including the operating point
