---
name: orchestrate-e2e
description: Orchestrates an end-to-end machine learning run from objective setup through dataset audit, data pipeline checks, training supervision, failure recovery, and evaluation gating. Use when asked to run or manage the full ML lifecycle, coordinate multiple ML skills, or deliver a Go/No-Go promotion decision with artifacts. Invoke this automatically when the user expresses a high-level goal like "train a model", "build something that predicts X", or "run the whole pipeline" — even if they haven't mentioned individual lifecycle steps. This skill gates all the sub-skills so the user gets end-to-end coverage without having to orchestrate manually.
argument-hint: "<objective> [--data SOURCE] [--label-col COLUMN] [--metric METRIC] [--train-cmd COMMAND] [--eval-target CHECKPOINT_OR_MODEL] [--baseline BASELINE] [--out-dir DIR] [--budget-hours N] [--max-retries N]"
disable-model-invocation: true
---

# Orchestrate E2E

Run a complete ML lifecycle with explicit gates, evidence capture, and promotion decisions.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<objective>` — plain-language business objective and model outcome
- `--data SOURCE` — dataset path, HF dataset, or DB target
- `--label-col COLUMN` — training target column
- `--metric METRIC` — primary selection metric (for example `f1`, `rmse`, `auprc`)
- `--train-cmd COMMAND` — canonical training command to execute
- `--eval-target` — checkpoint/model to evaluate
- `--baseline` — baseline checkpoint or results file for delta checks
- `--out-dir DIR` — output directory for run artifacts (default: `./reports/e2e-run`)
- `--budget-hours N` — wall-clock budget
- `--max-retries N` — max retries after failed runs (default: 2)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Establish the run contract

Before execution, generate a `run_id` (UUID or timestamp slug, e.g., `run-20260227-143022`) and create the `--out-dir`. Write a compact contract:

- Objective and business outcome
- Data source and label
- Primary metric and minimum acceptable threshold
- Runtime and retry budget
- Promotion criteria

If any contract field is missing, ask for the minimum clarification and continue.

### 2. Build a gate plan

Use [references/lifecycle-gates.md](references/lifecycle-gates.md) and define pass/fail criteria for each stage:

1) target readiness
2) experiment plan
3) non-ML baseline
4) dataset quality
5) data pipeline integrity
6) training stability
7) evaluation quality
8) interpretability and bias
9) promotion decision

Never skip gates without explicitly recording why.

**NO-GO halt policy**: if any gate returns `NO-GO`, immediately halt — do not execute subsequent gates. Write all artifacts collected so far, generate the partial HTML report, and return a final `NO-GO` decision that names the blocking gate and its actionable fixes.

### 3. Execute pre-training gates

Pass `--out-dir <out-dir> --run-id <run_id>` to every sub-skill so each writes its JSON artifact to the shared run directory.

Run and record:

- `review-target` — gate 1
- `plan-experiment` — gate 2
- `build-baseline` — gate 3
- `check-dataset-quality` — gate 4
- `check-data-pipeline` — gate 5

Apply the NO-GO halt policy after each gate.

### 4. Execute training gate (gate 6)

When `--train-cmd` is provided:

- Invoke `train-model` with the training command and any HP config from `plan-experiment.json` (if available in `--out-dir`)
- Pass `--out-dir <out-dir> --run-id <run_id>` so all sub-artifacts land in the shared directory
- `train-model` internally handles `babysit-training` monitoring and `check-failed-run` on failure
- Apply the NO-GO halt policy after `train-model` completes

When `--train-cmd` is missing, request it and wait.

### 5. Execute evaluation gate (gate 7)

Run `check-eval` on the selected checkpoint/model:

- Compare against baseline when provided; if `build-baseline.json` exists in `--out-dir`, pass it as `--baseline` automatically so the non-ML baseline score is the comparison floor
- Record regressions and improvements
- Produce a clear pass/fail against metric thresholds
- Apply the NO-GO halt policy after `check-eval` completes

### 5b. Execute interpretability gate (gate 8)

Run `explain-model` on the promoted checkpoint:

- Apply the NO-GO halt policy after `explain-model` completes

### 5c. Demonstrate value (optional)

If `--business-context` is provided or a business context is clearly inferable from the objective, invoke `demonstrate-value`:

- Pass `--out-dir <out-dir> --run-id <run_id>` and `--business-context` as appropriate
- This step does **not** affect the promotion decision — it is informational only
- If `demonstrate-value` fails, log the error and continue to the promotion step

### 5d. Recommend new approaches (always)

After all evaluation and interpretability gates complete, invoke `recommend-new-approaches`:

- Pass `--out-dir <out-dir> --run-id <run_id>` so it picks up all artifacts automatically
- This step does **not** affect the promotion decision — it is always informational and forward-looking
- If `recommend-new-approaches` fails, log the error and continue to the promotion step
- The recommendations should appear in the final run summary as "Next Experiments"

### 6. Issue promotion decision

Produce a single decision:

- `GO`: all required gates pass and quality bar is met
- `NO-GO`: any blocker remains or quality threshold is missed

Include confidence and top risks.

### 7. Write run artifacts

Write artifacts listed in [references/artifact-contract.md](references/artifact-contract.md), including:

- gate status table
- evidence links/paths
- recommended next commands

After all gates complete:

1. Write `run-summary.json` to `--out-dir` (schema in [../../references/schemas.md](../../references/schemas.md))
2. Generate the HTML report: `uv run plugins/agentic-ml/report-viewer/generate_report.py <out-dir>`
3. Report the `report.html` path in final output

### 8. Keep control until terminal state

Do not hand back partial progress. Continue until:

- a final GO/NO-GO decision is delivered, or
- a hard blocker requires user input that cannot be inferred.

## Output format

```text
E2E Run Summary
===============
Objective: <...>
Data: <...>
Label: <...>
Primary metric: <...>

Gate Status:
1) Target readiness:       PASS|FAIL|SKIPPED
2) Experiment plan:        PASS|FAIL|SKIPPED
3) Non-ML baseline:        PASS|FAIL|SKIPPED
4) Dataset quality:        PASS|FAIL|SKIPPED
5) Data pipeline:          PASS|FAIL|SKIPPED
6) Training stability:     PASS|FAIL|SKIPPED
7) Evaluation quality:     PASS|FAIL|SKIPPED
8) Interpretability/bias:  PASS|FAIL|SKIPPED
9) Promotion decision:     GO|NO-GO

Decision: GO|NO-GO
Confidence: high|medium|low

Top blockers/risks:
1) ...
2) ...

Report: <out-dir>/report.html

Next commands:
- ...
```

## Quick heuristics

- Dataset gate fails with leakage → do not proceed to pipeline or training; fix leakage first or the entire run is invalid
- Pipeline gate fails on label shift → most likely cause is seq2seq target not shifted by 1; check before retrying
- Training diverges in first 100 steps → do not burn budget retrying; pause and diagnose with `check-failed-run`
- Eval metric matches training metric suspiciously closely → re-check dataset gate for cross-split leakage
- Promotion threshold not set → default to "statistically significant improvement over baseline"; warn user and document assumption
- Baseline outperforms ML model → re-examine whether ML is needed (Rule 1 of Google's Rules of ML); surface as `high` finding
- Budget exceeded before eval → prefer a partial evaluation over none; document truncation in the run artifact

## Stop conditions

Stop when any of these is true:

- a gate returns `NO-GO` — halt immediately, write partial artifacts, generate partial HTML report
- all 9 gates complete and the final promotion decision is delivered
- user input is required for an explicit policy decision (for example, changing threshold or budget)

## Additional resources

- [references/lifecycle-gates.md](references/lifecycle-gates.md) — stage gates and pass/fail evidence
- [references/artifact-contract.md](references/artifact-contract.md) — required run artifact structure
