---
name: train-model
description: Launch and manage ML training with early stopping, hyperparameter configuration, and checkpoint management. Wraps babysit-training for monitoring and check-failed-run for failure recovery. Use when asked to train a model, start a training run, fine-tune a model, or execute a training command.
argument-hint: "<train-cmd> [--hp KEY=VALUE ...] [--early-stop-metric METRIC] [--early-stop-patience N] [--checkpoint-dir DIR] [--max-epochs N] [--max-steps N] [--out-dir DIR] [--run-id ID]"
---

# Train Model

Launch, configure, monitor, and recover a machine learning training run from start to terminal state.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<train-cmd>` — the training command to execute (e.g., `uv run train.py --config cfg.yaml`)
- `--hp KEY=VALUE` — hyperparameter override; may be repeated (e.g., `--hp lr=1e-4 --hp batch_size=32`)
- `--early-stop-metric METRIC` — metric to monitor for early stopping (e.g., `eval_loss`, `eval_f1`)
- `--early-stop-patience N` — stop after N eval cycles with no improvement (default: 5)
- `--checkpoint-dir DIR` — directory to look for and track checkpoints (default: inferred from train-cmd or `./checkpoints`)
- `--max-epochs N` — hard cap on training epochs (passed to train-cmd if supported)
- `--max-steps N` — hard cap on training steps (passed to train-cmd if supported)
- `--out-dir DIR` — output directory for all artifacts (default: `./reports/train-run`)
- `--run-id ID` — run ID shared across orchestrated skills (generated if not provided)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Parse and validate the training command

- Confirm `<train-cmd>` is provided; if missing, ask for it before proceeding
- Identify the training framework from the command (HuggingFace Trainer, PyTorch Lightning, plain PyTorch, JAX, etc.)
- Verify the command is executable (config files exist, entrypoint is reachable)

### 2. Apply hyperparameter overrides

For each `--hp KEY=VALUE`:

- If the training framework has a standard CLI override mechanism (e.g., `--learning_rate`, `--per_device_train_batch_size` for HF Trainer), inject the flag directly into the command
- If the framework uses a config file (YAML, JSON, TOML), read the config, apply the override, and write the modified config to `<out-dir>/hp-overrides.<ext>`
- Log each override applied: `HP override: lr=1e-4 (injected as --learning_rate 1e-4)`

### 3. Launch training

- Run the (possibly modified) training command using `uv run` where applicable
- Capture the PID or process handle
- Log the exact command that was executed to `<out-dir>/run-command.txt`
- Confirm the process starts successfully (no immediate crash within the first 10 seconds)

### 4. Delegate monitoring to babysit-training

Hand off to `babysit-training` immediately after the process is confirmed running:

- Pass the training log path or PID to `babysit-training`
- Forward `--interval`, `--max-interval`, `--no-backoff`, `--no-fix` flags if provided
- Pass `--out-dir <out-dir>` and `--run-id <run_id>` so the monitoring artifact lands in the shared directory

`babysit-training` runs until the process reaches a terminal state. Resume control once it exits.

### 5. Early stopping

If `--early-stop-metric` is set, monitor the metric independently on each eval checkpoint:

- Read eval metrics from the training log or a metrics file (e.g., `trainer_state.json` for HF Trainer)
- Track the best value seen so far
- If the metric does not improve for `--early-stop-patience` consecutive eval cycles, send SIGTERM to the training process and record `triggered: true` in the artifact
- Log: `Early stopping triggered at step <N> — <metric> did not improve for <patience> evals (best: <best_val> at step <best_step>)`

Early stopping is evaluated asynchronously alongside `babysit-training`. If `babysit-training` already signals a terminal state, skip early stopping checks.

### 6. Checkpoint management

- Scan `--checkpoint-dir` for checkpoints after training terminates
- Identify the **best checkpoint** by `--early-stop-metric` if set; otherwise use the most recent
- Record all checkpoints found with step numbers and metric values in the artifact
- Log the best checkpoint path: `Best checkpoint: <path> (step <N>, <metric>=<val>)`

### 7. Failure recovery

If `babysit-training` returns `NO-GO` (terminal state `FAILED` or `CANCELLED`):

- Automatically invoke `check-failed-run` with the training log and `--out-dir`
- Surface the root cause and approved recovery actions in the terminal summary
- Do **not** auto-apply high-risk fixes (hyperparameter changes, checkpoint rollbacks) — surface them as `needs-approval` actions

### 8. Terminal summary

After training completes (any terminal state), output:

```text
Training Complete
=================
Command: <train-cmd>
Terminal state: SUCCEEDED | FAILED | EARLY_STOPPED | CANCELLED
Steps completed: <N>/<total>
Epochs completed: <N>/<total>
Training duration: <HH:MM:SS>
Final metrics: <metric>=<value>, ...
Best checkpoint: <path> (step <N>)
Early stopping: triggered at step <N> | not triggered

Decision: GO | NO-GO
Confidence: high | medium | low
```

`GO`: terminal state is `SUCCEEDED` or `EARLY_STOPPED` with no unresolved critical anomalies.
`NO-GO`: terminal state is `FAILED`, `CANCELLED`, or `TIMEOUT` with unresolved blockers.

### JSON artifact

Write `train-model.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` when training succeeded or early-stopped without blockers; `NO-GO` on failure
- `train_cmd`, `hyperparameters`, `terminal_state`, `total_steps`, `total_epochs`
- `early_stopping`: `enabled`, `metric`, `patience`, `triggered`, `triggered_at_step`
- `final_metrics`, `best_checkpoint`, `all_checkpoints`
- `training_duration_seconds`, `babysit_training_ref`

## Example session

```
/ml-skills:train-model uv run train.py --config configs/gpt2-base.yaml --hp lr=3e-4 --hp batch_size=16 --early-stop-metric eval_loss --early-stop-patience 3 --checkpoint-dir ./checkpoints --out-dir ./reports/run-001

Parsed command: uv run train.py --config configs/gpt2-base.yaml
Framework detected: HuggingFace Trainer (from import in train.py)
HP overrides applied:
  lr=3e-4 → --learning_rate 3e-4
  batch_size=16 → --per_device_train_batch_size 16
Command written to: ./reports/run-001/run-command.txt

Launching training... PID 58291 confirmed running.
Handing off to babysit-training (log: ./logs/train.log, interval: 30s)

[babysit-training monitors until terminal state]

Training Complete
=================
Command: uv run train.py --config configs/gpt2-base.yaml --learning_rate 3e-4 ...
Terminal state: EARLY_STOPPED
Steps completed: 3200/10000
Epochs completed: 2/6
Training duration: 01:42:15
Final metrics: eval_loss=0.312, eval_f1=0.891
Best checkpoint: ./checkpoints/checkpoint-2800 (step 2800, eval_loss=0.308)
Early stopping: triggered at step 3200 — eval_loss did not improve for 3 evals

Decision: GO
Confidence: high
```

## Additional resources

- [babysit-training](../babysit-training/SKILL.md) — continuous monitoring skill (invoked internally)
- [check-failed-run](../check-failed-run/SKILL.md) — failure diagnosis skill (invoked on NO-GO)
- [../../references/schemas.md](../../references/schemas.md) — JSON artifact schema
- [../../references/vocabulary.md](../../references/vocabulary.md) — canonical enum values
