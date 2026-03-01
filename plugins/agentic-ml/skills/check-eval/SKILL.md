---
name: check-eval
description: Evaluates a model checkpoint using HF Trainer.evaluate(), lm-evaluation-harness, or a custom eval script. Loads the checkpoint, runs evaluation, parses results, computes deltas against a baseline, and produces a structured results report. Run this automatically after training completes or a checkpoint is saved to gate progression to the next lifecycle stage.
argument-hint: "[checkpoint-path | hf-model] [--task harness-task | --eval-script path] [--baseline CHECKPOINT_OR_RESULTS] [--split validation|test] [--batch-size N] [--device cuda|cpu|auto] [--dtype float16|bfloat16|float32]"
---

# Check Eval

Run structured evaluation on a model checkpoint and produce a results report with baseline comparison.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `path/to/checkpoint/` — local HuggingFace checkpoint directory
- `owner/model-name` — HuggingFace Hub model ID
- `--task TASK` — lm-evaluation-harness task(s), comma-separated (e.g., `hellaswag,arc_easy`)
- `--eval-script path/to/eval.py` — custom evaluation script to run
- `--baseline PATH_OR_FILE` — baseline checkpoint or JSON results file for delta comparison
- `--split` — dataset split to evaluate on (default: `validation` for HF Trainer, task-defined for harness)
- `--batch-size N` — per-device batch size (default: auto-detect from checkpoint config)
- `--device` — evaluation device (default: `auto`)
- `--dtype` — model dtype (default: `bfloat16` if supported, else `float32`)
- `--limit N` — max examples per task (useful for quick smoke tests)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Identify the evaluation strategy

Determine which evaluation path to use based on arguments:

- **HF Trainer.evaluate()**: checkpoint dir + no `--task` flag → use `Trainer.evaluate()` or `pipeline` on the eval split; see [references/hf-eval-patterns.md](references/hf-eval-patterns.md)
- **lm-evaluation-harness**: `--task` flag provided → compose `lm_eval` CLI command; see [references/harness-reference.md](references/harness-reference.md)
- **Custom script**: `--eval-script` flag → run the script with appropriate args; capture JSON output
- **Ambiguous**: ask the user which strategy before proceeding

### 2. Validate the checkpoint

Before running evaluation:

- Confirm the checkpoint directory exists and contains `config.json` + weights
- Check model architecture matches the task requirements
- Verify the tokenizer is present (for text models)
- Confirm device and dtype are compatible with the model size (estimate memory)
- Report estimated VRAM requirement

If the checkpoint is invalid or incomplete, stop and report the specific missing file.

### 3. Compose and run the evaluation command

For HF Trainer-based eval: write a short eval script using patterns from [references/hf-eval-patterns.md](references/hf-eval-patterns.md).

For lm-evaluation-harness: compose the `lm_eval` CLI command from [references/harness-reference.md](references/harness-reference.md). Always include:

- `--output_path` for reproducible result capture
- `--log_samples` for task-level debug
- `--batch_size auto` unless `--batch-size` is specified

Show the exact command before running it.

### 4. Parse and structure results

After evaluation completes:

- Extract metric names and values from the output JSON or stdout
- Compute deltas vs. baseline if `--baseline` is provided (use [scripts/compare-results.sh](scripts/compare-results.sh))
  - When `--baseline` points to a `build-baseline.json` artifact, extract `best_score` as the comparison floor; the non-ML baseline score is the minimum bar the ML model must exceed
- Flag any metrics that regressed vs. baseline
- Report per-task and aggregate results

### 5. Report format

```text
Eval Report
===========
Checkpoint: <path or model ID>
Strategy: <HF Trainer | lm-evaluation-harness | custom>
Device: <device>  |  Dtype: <dtype>
Tasks: <task list or eval split>
Baseline: <baseline path or none>

Results:
| Task / Metric     | Score    | Baseline | Delta  | Status   |
|-------------------|----------|----------|--------|----------|
| <task>/<metric>   | <value>  | <value>  | <±Δ>  | ✓ / ↓ / new |

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

`GO`: all metrics meet thresholds, no regressions vs. baseline.
`CONDITIONAL`: minor regressions on secondary metrics; primary metric threshold met.
`NO-GO`: primary metric threshold not met or checkpoint invalid.

If no baseline:

```text
Results:
| Task / Metric   | Score   |
|-----------------|---------|
| ...             | ...     |
```

### 6. Fix policy

Apply without approval:

- Running read-only eval commands
- Creating temporary eval scripts that do not modify the checkpoint

Require user approval before:

- Modifying the checkpoint (merging adapters, quantizing, etc.)
- Uploading results to W&B, MLflow, or HuggingFace Hub
- Running on the test split (prefer validation; test should be held out)

### 7. Stop conditions

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
/ml-skills:check-eval ./runs/llama-ft/checkpoint-5000 --task hellaswag,arc_easy,mmlu --dtype bfloat16 --baseline ./runs/llama-ft/checkpoint-2500

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
/ml-skills:check-eval ./runs/bert-classifier/checkpoint-final --split validation --batch-size 32

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

### JSON artifact

Write `check-eval.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` / `NO-GO` / `CONDITIONAL`
- `results`: one entry per task/metric with score, baseline, delta, and regressed flag
- `regressions`: list of metric names that regressed vs. baseline
- `findings`: one entry per regression (severity `high`) and per warning/note (severity `medium` or `low`)
