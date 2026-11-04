---
name: orchestrate-e2e
description: Orchestrates an end-to-end ML run, from choosing the approach and defining the target, through dataset audit, baseline, experiment plan, pipeline checks, training supervision, failure recovery, evaluation with confidence intervals, interpretability, and deployment readiness, to a final promotion decision on a locked test set with an ML Test Score. Every headline number is recorded in a re-runnable showboat evidence notebook that is verified before promotion. Adapts to the user's level (junior, senior, staff) and autonomy setting. Run it with /orchestrate-e2e when you want the full ML lifecycle coordinated with explicit gates and a Go/No-Go decision backed by artifacts.
argument-hint: "<objective> [--data SOURCE] [--label-col COLUMN] [--metric METRIC] [--train-cmd COMMAND] [--eval-target CHECKPOINT_OR_MODEL] [--baseline BASELINE] [--business-context TEXT] [--approach APPROACH] [--level junior|senior|staff] [--autonomy review-every-gate|review-key-gates|autonomous] [--latency-budget-ms N] [--out-dir DIR] [--budget-hours N] [--max-retries N]"
disable-model-invocation: true
---

# Orchestrate E2E

Run a complete ML lifecycle with explicit gates, evidence capture, human checkpoints, and a promotion decision.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<objective>` — plain-language business objective and model outcome
- `--data SOURCE` — dataset path, HF dataset, or DB target
- `--label-col COLUMN` — training target column
- `--metric METRIC` — primary selection metric (for example `f1`, `rmse`, `auprc`)
- `--train-cmd COMMAND` — canonical training command to execute (optional for tabular data; see gate 6)
- `--eval-target` — checkpoint/model to evaluate
- `--baseline` — baseline checkpoint or results file for delta checks
- `--business-context TEXT` — plain-language business stakes; enables the optional `demonstrate-value` step
- `--approach APPROACH` — skip gate 0 when the approach is already decided (an approach ID from [vocabulary.md](../../references/vocabulary.md#approach))
- `--level junior|senior|staff` — how to work with the user (see [levels.md](../../references/levels.md))
- `--autonomy review-every-gate|review-key-gates|autonomous` — when to pause for review (default: from the level)
- `--latency-budget-ms N` — serving latency budget passed to gate 9
- `--out-dir DIR` — output directory for run artifacts (default: `./reports/e2e-run`)
- `--budget-hours N` — wall-clock budget
- `--max-retries N` — max retries of the training gate (gate 6) after a failed run (default: 2)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Establish the run contract

Before execution, generate a `run_id` (UUID or timestamp slug, e.g., `run-20260227-143022`) and create the `--out-dir`.

Resolve the level and autonomy (see [../../references/levels.md](../../references/levels.md)):

- Use `--level`, then `.claude/agentic-ml.local.md`.
- If neither is set, ask once and offer to save the answer to `.claude/agentic-ml.local.md`.
- Autonomy defaults from the level: `junior` → `review-every-gate`, `senior` → `review-key-gates`, `staff` → `autonomous`. `--autonomy` overrides it.

Write `run-contract.md`:

- Objective and business outcome
- Level and autonomy
- Data source and label
- Primary metric and minimum acceptable threshold
- Runtime and retry budget
- Promotion criteria

If any contract field is missing, ask for the minimum clarification and continue.

Start the run's evidence notebook (see [../../references/evidence-notebook.md](../../references/evidence-notebook.md)):

```bash
uvx showboat --workdir <out-dir> init <out-dir>/evidence.md "Evidence — <objective> (<run_id>)"
uvx showboat --workdir <out-dir> note <out-dir>/evidence.md "## Run contract
<objective, data, label, metric and threshold, level, autonomy>"
```

Every sub-skill appends its own section. Re-running the notebook is how a reviewer checks the run.

### 2. Build a gate plan

Use [references/lifecycle-gates.md](references/lifecycle-gates.md) and define pass/fail criteria for each gate:

0) approach selection
1) target readiness and split lock
2) dataset quality
3) baseline
4) experiment plan (4b: feature engineering, when needed)
5) data pipeline integrity
6) training stability
7) evaluation quality (validation)
8) interpretability and bias
9) deployment readiness
10) promotion decision (final test evaluation and sign-off)

Follow `select-approach.json`'s `lifecycle_map`: gates listed in `skipped` are recorded as `SKIPPED` with the reason. Never skip gates without explicitly recording why.

Pass `--out-dir <out-dir> --run-id <run_id> --level <level>` to every sub-skill so each writes its JSON artifact to the shared run directory.

**NO-GO halt policy**: if any gate returns `NO-GO`, immediately halt — do not execute subsequent gates. Write all artifacts collected so far, generate the partial HTML report, and return a final `NO-GO` decision that names the blocking gate and its actionable fixes.

**CONDITIONAL policy**: if a gate returns `CONDITIONAL`, continue to the next gate, record the gate as `PASS` with its caveats in `gate-status.md`, and carry every caveat into `top_risks` in `run-summary.json` and the final summary. Never drop a caveat silently.

**Evidence**: after each gate, check that its section exists in `evidence.md` and covers its headline numbers and `blocker`/`high` findings. If it is missing, ask the sub-skill to add it before moving on.

**Review pauses**: pause where the autonomy setting requires (see [levels.md](../../references/levels.md#autonomy)). Show the review card and wait for the user. With `review-key-gates`, pause after gate 1, after gate 5 (before training spend), and at gate 10. Every setting pauses on `NO-GO`, on `needs-approval` actions, and at promotion.

### 3. Select the approach (gate 0)

Run `select-approach` unless `--approach` is given.

- If it recommends `no-ml`, run gates 1–3 to measure the rule, then stop with a recommendation to ship the rule. This is a valid, successful outcome.
- If the plugin does not cover parts of the chosen approach (`not_covered`), list them in the contract and in `top_risks`.

### 4. Execute pre-training gates (gates 1–5)

Run and record:

- `review-target` — gate 1. Defines the target and metric, creates the split with `make_splits.py`, and locks the test set.
- `check-dataset-quality` — gate 2. Audits the data before anything is computed on it, and saves the data contract and drift baseline.
- `build-baseline` — gate 3. Fit on `train`, scored on `val`; the best score becomes the floor for the plan.
- `plan-experiment` — gate 4. Pass `build-baseline.json` and the dataset profile so candidates and compute estimates reflect the real data.
- `feature-engineer` — gate 4b, **only when needed**: invoke it when the data is raw (multiple source tables, `--db-url`/`--tables`, or no agreed feature set yet). Skip it when the dataset is already a model-ready feature table, and record `SKIPPED` with that reason.
- `check-data-pipeline` — gate 5. Uses the tabular checks for scikit-learn/LightGBM/XGBoost pipelines.

Apply the NO-GO halt policy after each gate.

### 5. Execute the training gate (gate 6)

Invoke `train-model`:

- Pass the training command and the HP config from `plan-experiment.json`. Pass `--sweep` when the plan includes a search.
- When `--train-cmd` is missing and the data is tabular, `train-model` offers its leakage-safe `train_tabular.py` scaffold. At `junior` it proceeds after explaining; at `senior`/`staff` it asks first. For other data, request the command and wait.
- `train-model` runs pre-flight checks, records seeds and provenance, uses native early stopping, delegates monitoring to `babysit-training`, and runs `check-failed-run` on failure.
- Apply the NO-GO halt policy after `train-model` completes.

### 6. Execute the evaluation gate (gate 7)

Run `check-eval` on `val` — **not** `test`:

- metric with a 95% interval and a paired delta against the best baseline (`build-baseline.json` predictions)
- slices (protected attributes and key segments), calibration, and the threshold table
- choose the operating point on `val` and record it
- Apply the NO-GO halt policy after `check-eval` completes.

### 7. Execute the interpretability gate (gate 8)

Run `explain-model` on the selected model. Apply the NO-GO halt policy after it completes.

### 8. Execute the deployment-readiness gate (gate 9)

Run `check-deployment-readiness` with `--latency-budget-ms` when given:

- training/serving parity in a fresh process
- latency and memory budgets
- contract check
- monitoring plan
- rollout and rollback plan

Apply the NO-GO halt policy after it completes.

### 9. Demonstrate value (optional)

If `--business-context` is provided or a business context is clearly inferable from the objective, invoke `demonstrate-value`:

- Pass `--out-dir <out-dir> --run-id <run_id>` and `--business-context` as appropriate
- This step does **not** affect the promotion decision — it is informational only
- If `demonstrate-value` fails, log the error and continue to the promotion step

### 10. Recommend new approaches (always)

After the evaluation, interpretability, and readiness gates, invoke `recommend-new-approaches`:

- Pass `--out-dir <out-dir> --run-id <run_id>` so it picks up all artifacts automatically
- This step does **not** affect the promotion decision — it is always informational and forward-looking
- If `recommend-new-approaches` fails, log the error and continue to the promotion step
- The recommendations should appear in the final run summary as "Next Experiments"

### 11. Promotion decision (gate 10)

1. Show the review card with the gate results, the `val` metrics with intervals, the operating point, and the top risks. Ask the user to accept the model choice and threshold. This pause happens at every autonomy level.
2. Verify the evidence notebook:

   ```bash
   uvx showboat --workdir <out-dir> verify <out-dir>/evidence.md > <out-dir>/evidence-verify.txt 2>&1; echo $?
   ```

   Exit `0` means every recorded number reproduced. On exit `1`, show the changed blocks from `evidence-verify.txt` and record a `high` finding. If a headline metric, the test hash, or a blocker finding changed, stop with `NO-GO` until it is explained.
3. After acceptance, run `check-eval --final` **once**, and append its section to the notebook. It writes test predictions for the model and the best baseline, verifies the test hash against the split manifest, and reports the final metrics with intervals.
4. Decide:
   - `GO`: all required gates passed, the final test result meets the promotion criteria (the metric meets the threshold and beats the baseline with an interval excluding zero), and the evidence notebook verified
   - `CONDITIONAL`: it meets the threshold but carries caveats (an interval including zero, flagged slices, missing monitoring owners, or a notebook written without showboat)
   - `NO-GO`: any blocker remains, the final test result misses the threshold, or the test hash does not match
5. The user signs off on the final decision; record who accepted it and when in `decision.md`.

Include confidence and top risks.

### 12. Score production readiness (ML Test Score)

Score the run against Google's ML Test Score rubric using [references/ml-test-score.md](references/ml-test-score.md):

- 28 tests in 4 sections
- 0.5 points per test done manually in this run with evidence
- 1 point only if it is automated in the user's own pipeline
- the final score is the lowest section score

Award points only with an evidence path. Write the result to `run-summary.json` as `ml_test_score`. The score informs the decision and the next steps; it does not override the gate results.

### 13. Write run artifacts

Write artifacts listed in [references/artifact-contract.md](references/artifact-contract.md), including:

- gate status table
- evidence links/paths
- recommended next commands

After all gates complete:

1. Write `run-summary.json` to `--out-dir` (schema in [../../references/schemas.md](../../references/schemas.md)), including `evidence`: the notebook path, block count, and verify result
2. Generate the HTML report: `uv run "${CLAUDE_SKILL_DIR}/scripts/generate_report.py" <out-dir>`
3. Report the `report.html` path in final output

### 14. Keep control until terminal state

Do not hand back partial progress. Continue until:

- a final GO/NO-GO decision is delivered, or
- a hard blocker or a review pause requires user input that cannot be inferred.

## Output format

```text
E2E Run Summary
===============
Objective: <...>
Approach: <approach>   Level: <level>   Autonomy: <autonomy>
Data: <...>
Label: <...>
Primary metric: <...>

Gate Status:
0) Approach selection:     PASS|FAIL|SKIPPED
1) Target readiness:       PASS|FAIL|SKIPPED
2) Dataset quality:        PASS|FAIL|SKIPPED
3) Baseline:               PASS|FAIL|SKIPPED
4) Experiment plan:        PASS|FAIL|SKIPPED
5) Data pipeline:          PASS|FAIL|SKIPPED
6) Training stability:     PASS|FAIL|SKIPPED
7) Evaluation (val):       PASS|FAIL|SKIPPED
8) Interpretability/bias:  PASS|FAIL|SKIPPED
9) Deployment readiness:   PASS|FAIL|SKIPPED
10) Promotion (test):      GO|CONDITIONAL|NO-GO

Final test: <metric> = <value> [<lo>, <hi>]  vs baseline <value>  delta <Δ> [<lo>, <hi>]
ML Test Score: data <x> | model <y> | infra <z> | monitoring <w> → final <min>
Evidence: <out-dir>/evidence.md — <n> blocks, verified ✓ | <k> blocks changed | not verifiable

Decision: GO|CONDITIONAL|NO-GO
Confidence: high|medium|low
Signed off by: <user> at <time>

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
- Validation metric suspiciously close to perfect → re-check the dataset gate for leakage before trusting it
- Promotion threshold not set → default to "beats the best baseline with a 95% interval excluding zero"; warn the user and document the assumption
- Baseline outperforms ML model → re-examine whether ML is needed (Rule 1 of Google's Rules of ML); surface as `high` finding
- Budget exceeded before eval → prefer a partial evaluation over none; document truncation in the run artifact
- A sub-skill reports a number with no command behind it in `evidence.md` → treat the number as unverified until it is added
- User asks to "check test once more" after the final evaluation → that is test reuse; record it as a `high` finding, and the decision can be at most `CONDITIONAL`

## Stop conditions

Stop when any of these is true:

- a gate returns `NO-GO` — halt immediately, write partial artifacts, generate partial HTML report
- all gates complete and the final promotion decision is signed off
- `select-approach` recommends `no-ml` and the rule has been measured
- user input is required for an explicit policy decision (for example, changing threshold or budget) or at a review pause

## Additional resources

- [references/lifecycle-gates.md](references/lifecycle-gates.md) — stage gates and pass/fail evidence
- [references/artifact-contract.md](references/artifact-contract.md) — required run artifact structure
- [references/ml-test-score.md](references/ml-test-score.md) — ML Test Score rubric mapped to gates and artifacts
- [../../references/levels.md](../../references/levels.md) — levels, autonomy, and the review card
- [../../references/evaluation-protocol.md](../../references/evaluation-protocol.md) — locked test set, intervals, slices, final evaluation
- [../../references/evidence-notebook.md](../../references/evidence-notebook.md) — the run's re-runnable evidence notebook
- [scripts/generate_report.py](scripts/generate_report.py) — builds `report.html` from the run's JSON artifacts
