---
name: check-eval
description: Evaluates a trained model — a tabular model (sklearn, LightGBM, XGBoost), a predictions file, an HF checkpoint via Trainer.evaluate(), lm-evaluation-harness, or a custom eval script. Reports metrics with bootstrap confidence intervals, a paired comparison against the baseline, slice metrics, calibration, and the operating point, and runs the one-time final test-set evaluation. Run this automatically after training completes or a checkpoint is saved to gate progression to the next lifecycle stage.
argument-hint: "[checkpoint-path | hf-model | model.joblib] [--predictions CSV] [--data PATH --label-col COL] [--metric METRIC] [--slice-cols C1,C2] [--final] [--task harness-task | --eval-script path] [--baseline CHECKPOINT_OR_RESULTS] [--split validation|test] [--batch-size N] [--device cuda|cpu|auto] [--dtype float16|bfloat16|float32] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Check Eval

Run structured evaluation on a model checkpoint and produce a results report with baseline comparison.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `path/to/checkpoint/` — local HuggingFace checkpoint directory
- `owner/model-name` — HuggingFace Hub model ID
- `path/to/model.joblib` (or `.pkl`) — a fitted tabular model or pipeline (sklearn API)
- `--predictions PATH` — a predictions CSV in the [shared format](../../references/evaluation-protocol.md#predictions-file); evaluate it directly
- `--data PATH` / `--label-col COL` — raw data for scoring a tabular model
- `--metric METRIC` — primary metric (default: from `review-target.json`)
- `--slice-cols C1,C2` — columns to evaluate by slice (default: protected attributes and key segments from upstream artifacts)
- `--final` — the one-time test-set evaluation (see step 4)
- `--task TASK` — lm-evaluation-harness task(s), comma-separated (e.g., `hellaswag,arc_easy`)
- `--eval-script path/to/eval.py` — custom evaluation script to run
- `--baseline PATH_OR_FILE` — baseline checkpoint or JSON results file for delta comparison
- `--split` — dataset split to evaluate on (default: `validation` for HF Trainer, task-defined for harness)
- `--batch-size N` — per-device batch size (default: auto-detect from checkpoint config)
- `--device` — evaluation device (default: `auto`)
- `--dtype` — model dtype (default: `bfloat16` if supported, else `float32`)
- `--limit N` — max examples per task (useful for quick smoke tests)

Target: `$ARGUMENTS`

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- `junior`: explain what the confidence interval means and why the test set is used only once.
- `staff`: report the delta CI and whether it changes the decision.

## Your responsibilities

### 1. Identify the evaluation strategy

Determine which evaluation path to use based on arguments:

- **Tabular model**: a `.joblib`/`.pkl` model plus `--data` → write predictions for the split with `uv run "${CLAUDE_PLUGIN_ROOT}/skills/train-model/scripts/train_tabular.py" predict --model <model> --data <path> --splits <out-dir>/splits --split val --label-col <col> --out <out-dir>/predictions/model_val.csv` (or the model's own predict code), then evaluate the file
- **Predictions file**: `--predictions` → evaluate it directly
- **HF Trainer.evaluate()**: checkpoint dir + no `--task` flag → use `Trainer.evaluate()` or `pipeline` on the eval split; see [references/hf-eval-patterns.md](references/hf-eval-patterns.md)
- **lm-evaluation-harness**: `--task` flag provided → compose `lm_eval` CLI command; see [references/harness-reference.md](references/harness-reference.md)
- **Custom script**: `--eval-script` flag → run the script with appropriate args; capture JSON output
- **Ambiguous**: ask the user which strategy before proceeding

### 2. Validate the model or inputs

Before running evaluation:

- **HF checkpoint:** the directory contains `config.json` plus weights; the architecture matches the task; the tokenizer is present (text models); the device and dtype fit the model size (report the estimated VRAM)
- **Tabular model:** it loads with `joblib` and exposes `predict` / `predict_proba`. If it was saved with LightGBM, XGBoost, or CatBoost, add that library (`uv run --with lightgbm ...`).
- **Predictions file:** it has `row_key`, `y_true`, and `y_score` / `score_<class>` / `y_pred` as the task needs

If the model or file is invalid or incomplete, stop and report exactly what is missing.

### 3. Compose and run the evaluation command

For HF Trainer-based eval: write a short eval script using patterns from [references/hf-eval-patterns.md](references/hf-eval-patterns.md).

For lm-evaluation-harness: compose the `lm_eval` CLI command from [references/harness-reference.md](references/harness-reference.md). Always include:

- `--output_path` for reproducible result capture
- `--log_samples` for task-level debug
- `--batch_size auto` unless `--batch-size` is specified

Show the exact command before running it.

### 4. Apply the evaluation protocol

Follow [../../references/evaluation-protocol.md](../../references/evaluation-protocol.md). For classification and regression predictions, compute everything with one command:

```bash
uv run "${CLAUDE_SKILL_DIR}/scripts/eval_report.py" --pred <out-dir>/predictions/model_val.csv \
  --metric <metric> --baseline-pred <out-dir>/predictions/<best-baseline>_val.csv \
  --slices <data> --slice-cols <c1,c2> --key-col <row-key-col> --threshold-grid \
  --split-manifest <out-dir>/splits/split-manifest.json --expect-split val \
  --out <out-dir>/eval-metrics-val.json
```

It reports:

- the metric with a 95% bootstrap interval
- the paired delta against the baseline
- slice metrics, with weak slices flagged
- calibration (Brier, ECE)
- a threshold table for choosing the operating point on `val`

With many slice values, lower `--n-boot` (e.g. 500) to keep it fast. Prediction files must write `row_key` exactly as `split_assignments.csv` does (compared as strings).

For harness and custom evaluations, report the harness's standard errors, or bootstrap per-example scores when `--log_samples` output is available.

**Validation vs. final.** Without `--final`, evaluate on `val` only. With `--final`:

- Only after the user has accepted the model choice and threshold.
- Write test predictions once (e.g. `train_tabular.py predict --split test`).
- Apply the best baseline's `rule` from `build-baseline.json` to the same test rows and write `predictions/baseline_<method>_test.csv`, so the final delta is a paired comparison.
- Run `eval_report.py` with `--expect-split test`. It verifies `test_keys_sha256` against the manifest.
- Record `protocol.test_evaluations`. If a previous final evaluation exists in `--out-dir`, this is test reuse: a `high` finding, and the decision is at most `CONDITIONAL`.

### 5. Parse and structure results

After evaluation completes:

- Extract metric names and values from the output JSON or stdout
- Compute deltas vs. baseline if `--baseline` is provided (use [`"${CLAUDE_SKILL_DIR}/scripts/compare-results.sh"`](scripts/compare-results.sh))
  - When `--baseline` points to a `build-baseline.json` artifact, use the best baseline's `predictions_path` for the paired comparison in step 4. If it has no predictions file, fall back to `best_score` as the floor and note that the delta has no interval.
- Flag any metrics that regressed vs. baseline
- Report per-task and aggregate results

### 6. Report format

```text
Eval Report
===========
Checkpoint: <path or model ID>
Strategy: <tabular | predictions | HF Trainer | lm-evaluation-harness | custom>
Device: <device>  |  Dtype: <dtype>
Tasks: <task list or eval split>
Split: <val | test (final)>  |  n=<rows> (<positives> positives)  |  test hash: <match | mismatch | n/a>
Baseline: <baseline path or none>

Results (95% bootstrap CI):
| Task / Metric     | Score               | Baseline            | Delta                 | Status   |
|-------------------|---------------------|---------------------|-----------------------|----------|
| <task>/<metric>   | <value> [<lo>, <hi>] | <value> [<lo>, <hi>] | <±Δ> [<lo>, <hi>]      | ✓ / ~ / ↓ / new |

Slices (flagged when the CI upper bound is below the overall score):
| Slice | n | Score [CI] | Flag |

Calibration: Brier=<...>  ECE=<...>
Operating point (chosen on val): threshold=<t>  precision=<p>  recall=<r>  flagged=<rate>

Summary:
- Best gain: <metric> +Δ
- Improvement over non-ML baseline: +X.X pp (when build-baseline.json is the --baseline)
- Regressions: <metric> -Δ (investigate)
- New metrics (no baseline): <list>

Notes:
- <any warnings about truncation, OOM, skipped examples, etc.>

Decision: GO | NO-GO | CONDITIONAL
Confidence: high|medium|low
```

`✓` = delta interval excludes zero in the better direction; `~` = better point estimate but the interval includes zero; `↓` = worse.

- `GO`: the primary metric meets the promotion threshold, and the delta against the baseline is significant (its interval excludes zero in the better direction); no flagged slices; no secondary regressions.
- `CONDITIONAL`: the primary metric meets the threshold, but at least one of these holds:
  - the delta's interval includes zero
  - a slice is flagged
  - a secondary metric regressed
  - fewer than 30 positives in the evaluation set
  - the test set was evaluated more than once
- `NO-GO`: the primary metric misses the threshold, the model is worse than the baseline, the test hash does not match the manifest, or the model or inputs are invalid.

If no baseline:

```text
Results:
| Task / Metric   | Score   |
|-----------------|---------|
| ...             | ...     |
```

### 7. Fix policy

Apply without approval:

- Running read-only eval commands
- Creating temporary eval scripts that do not modify the checkpoint

Require user approval before:

- Modifying the checkpoint (merging adapters, quantizing, etc.)
- Uploading results to W&B, MLflow, or HuggingFace Hub
- Running the final test-set evaluation (`--final`) — only once, and only after the user has accepted the model choice and threshold

### 8. Stop conditions

Stop when:

- A complete results report is delivered
- The checkpoint is invalid and the specific error is reported
- The evaluation fails and the failure is diagnosed (OOM, missing dependency, etc.)
- User decision is required (e.g., ambiguous eval strategy, test split usage)

## Quick heuristics

- Eval loss much higher than train loss → overfitting, wrong eval split, or data contamination
- Harness score below random baseline → label format mismatch or wrong task name
- Memory OOM during eval but not training → eval batch size inherits train batch size; set `per_device_eval_batch_size` explicitly
- Different scores on same data across runs → generation temperature > 0 or batch-size-dependent normalization; use `--batch_size 1` to isolate
- `lm_eval` task name typo → harness exits with `ValueError: no tasks matching`; check `uv run lm_eval --list-tasks`

## Examples

```text
/agentic-ml:check-eval ./runs/llama-ft/checkpoint-5000 --task hellaswag,arc_easy,mmlu --dtype bfloat16 --baseline ./runs/llama-ft/checkpoint-2500

Checkpoint: ./runs/llama-ft/checkpoint-5000 (LlamaForCausalLM, 7B params)
Strategy: lm-evaluation-harness
Command:
  uv run lm_eval --model hf \
    --model_args pretrained=./runs/llama-ft/checkpoint-5000,dtype=bfloat16 \
    --tasks hellaswag,arc_easy,mmlu \
    --batch_size auto \
    --output_path ./eval_results/checkpoint-5000.json \
    --log_samples

[Running... 14m 32s]

Eval Report
===========
Checkpoint: ./runs/llama-ft/checkpoint-5000
Baseline:   ./runs/llama-ft/checkpoint-2500

Results:
| Task / Metric      | Score  | Baseline | Delta  | Status |
|--------------------|--------|----------|--------|--------|
| hellaswag/acc_norm | 0.7823 | 0.7441   | +0.038 | ✓      |
| arc_easy/acc_norm  | 0.7912 | 0.7905   | +0.001 | ✓      |
| mmlu/acc            | 0.5231 | 0.5398   | -0.017 | ↓      |

Summary:
- Best gain: hellaswag +3.8pp
- Regressions: mmlu -1.7pp (investigate — may need more training or MMLU-specific tuning)
```

```text
/agentic-ml:check-eval ./runs/bert-classifier/checkpoint-final --split validation --batch-size 32

Checkpoint: ./runs/bert-classifier/checkpoint-final (BertForSequenceClassification)
Strategy: HF Trainer.evaluate()

Eval Report
===========
| Metric    | Score  |
|-----------|--------|
| eval_loss | 0.2341 |
| eval_f1   | 0.8812 |
| eval_acc  | 0.9103 |

No baseline provided. Use --baseline to compute deltas.
```

## Additional resources

- [references/hf-eval-patterns.md](references/hf-eval-patterns.md) — Loading and evaluating HF model types, precision, device mapping
- [references/harness-reference.md](references/harness-reference.md) — lm-evaluation-harness CLI reference, tasks, output parsing
- [scripts/compare-results.sh](scripts/compare-results.sh) — JSON result diff with delta formatting
- [scripts/eval_report.py](scripts/eval_report.py) — metrics with bootstrap intervals, paired baseline delta, slices, calibration, threshold table, and split check
- [../../references/evaluation-protocol.md](../../references/evaluation-protocol.md) — locked test set, intervals, slices, and the one-time final evaluation

### Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- `eval_report.py` on `val` with the baseline and split check and `--out /dev/null`, printing the metric, delta, and split-check lines
- the flagged slices and the chosen operating point
- final evaluation: the same command on `predictions/model_test.csv` with `--expect-split test` — this recomputes the saved result, it is not a new evaluation
- harness or custom evaluations: a note with the command, and an `exec` block printing the key metrics and sha256 of the results file

### JSON artifact

Write `check-eval.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` / `NO-GO` / `CONDITIONAL`
- `results`: one entry per task/metric with `score`, `ci`, `n`, `baseline_score`, `baseline_ci`, `delta`, `delta_ci`, and `regressed`
- `protocol`: `split`, `final`, `test_keys_sha256_match`, `test_evaluations`
- `calibration`, `slices`, `operating_point` (from `eval_report.py` output; also keep the full output as `eval-metrics-<split>.json` in `--out-dir`)
- `regressions`: list of metric names that regressed vs. baseline
- `findings`: one entry per regression (severity `high`) and per warning/note (severity `medium` or `low`)
