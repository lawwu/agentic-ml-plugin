---
name: train-model
description: Launch and manage ML training with pre-flight checks, native early stopping, hyperparameter sweeps, experiment tracking, provenance, and checkpoint management. Includes a leakage-safe tabular training scaffold when there is no training script yet. Wraps babysit-training for monitoring and check-failed-run for failure recovery. Use when asked to train a model, start a training run, fine-tune a model, or execute a training command.
argument-hint: "[<train-cmd>] [--hp KEY=VALUE ...] [--sweep] [--seed N] [--early-stop-metric METRIC] [--early-stop-patience N] [--checkpoint-dir DIR] [--max-epochs N] [--max-steps N] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Train Model

Launch, configure, monitor, and recover a machine learning training run from start to terminal state.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<train-cmd>` — the training command to execute (e.g., `uv run train.py --config cfg.yaml`); optional for tabular data, where the bundled scaffold can be used (step 1)
- `--sweep` — run the hyperparameter search from `plan-experiment.json` before the final training run (step 8)
- `--seed N` — random seed (default: 42)
- `--hp KEY=VALUE` — hyperparameter override; may be repeated (e.g., `--hp lr=1e-4 --hp batch_size=32`)
- `--early-stop-metric METRIC` — metric to monitor for early stopping (e.g., `eval_loss`, `eval_f1`)
- `--early-stop-patience N` — stop after N eval cycles with no improvement (default: 5)
- `--checkpoint-dir DIR` — directory to look for and track checkpoints (default: inferred from train-cmd or `./checkpoints`)
- `--max-epochs N` — hard cap on training epochs (passed to train-cmd if supported)
- `--max-steps N` — hard cap on training steps (passed to train-cmd if supported)
- `--out-dir DIR` — output directory for all artifacts (default: `./reports/train-run`)
- `--run-id ID` — run ID shared across orchestrated skills (generated if not provided)

Target: `$ARGUMENTS`

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- `junior`: if there is no training command, copy the `train_tabular.py` scaffold into the project and walk through it before running.
- `senior`/`staff`: use the user's training command; ask for one if missing.

## Your responsibilities

### 1. Resolve the training command

If `<train-cmd>` is provided:

- Identify the training framework (HuggingFace Trainer, PyTorch Lightning, plain PyTorch, JAX, scikit-learn, LightGBM, XGBoost, etc.)
- Verify the command is executable (config files exist, entrypoint is reachable)

If it is missing and the data is tabular with a split from `review-target`:

- Use the bundled leakage-safe scaffold. Copy `"${CLAUDE_SKILL_DIR}/scripts/train_tabular.py"` into the project (e.g. `./train_tabular.py`) so the code is visible, versioned, and editable. Then run:

  ```bash
  uv run train_tabular.py train --data <path> --splits <out-dir>/splits --label-col <col> \
    --task binary|multiclass|regression --model lightgbm|hgb|logreg --seed 42 --out-dir <out-dir>
  ```

  It fits preprocessing inside an sklearn Pipeline on `train` only, early-stops on `val`, never reads `test`, and writes `<out-dir>/model.joblib`, `<out-dir>/predictions/model_val.csv`, `train-metrics.json`, and `train-config.json`. Notes:

  - Input is CSV; convert Parquet first.
  - Add `--cv-folds 5` for cross-validation that matches the split strategy.
  - Pass leaky or post-outcome columns flagged by `check-dataset-quality` in `--drop-cols`.
  - For group or time splits prefer `--model lightgbm`: it early-stops on the real `val` split, while `hgb`'s internal early-stopping holdout is a random row sample.
  - LightGBM needs `uv run --with lightgbm`.
  - `train-metrics.json` includes a leakage note when the validation score is near-perfect; treat it as a stop sign.
- `junior`: walk through what the script does before running it. `senior`/`staff`: propose it and ask before copying it into the project.

Otherwise, ask for the training command.

For every command:

- Run it in the project's own environment (uv, conda, poetry — follow `.claude/agentic-ml.local.md` if present). Do not wrap it in `uv run` unless the project uses uv.
- Check how it loads data. If it reads or evaluates on the test split during training, flag a `high` finding and ask before launching — see [../../references/evaluation-protocol.md](../../references/evaluation-protocol.md).

### 2. Apply hyperparameter overrides

For each `--hp KEY=VALUE`:

- If the training framework has a standard CLI override mechanism (e.g., `--learning_rate`, `--per_device_train_batch_size` for HF Trainer), inject the flag directly into the command
- If the framework uses a config file (YAML, JSON, TOML), read the config, apply the override, and write the modified config to `<out-dir>/hp-overrides.<ext>`
- Log each override applied: `HP override: lr=1e-4 (injected as --learning_rate 1e-4)`

### 3. Run pre-flight checks before spending compute

Run the cheap checks in [references/preflight-checks.md](references/preflight-checks.md) before the full run:

- **Neural networks:**
  - the loss at initialization is close to its expected value (≈ ln C for C-class cross-entropy)
  - the model can overfit one small batch
  - a short run saves a checkpoint, resumes from it, and continues at the same step and loss
- **Gradient-boosted trees and scikit-learn:**
  - a fit on a small sample completes
  - predictions are not constant
  - the feature count matches the data contract
  - a near-perfect validation score (e.g. ROC-AUC ≥ 0.99) after the sample fit triggers a leakage check before going further

Record each check as `pass` / `fail` / `skipped` in `preflight`. A failed pre-flight check is a `NO-GO` for the full run unless the user explicitly accepts it.

### 4. Seed, record provenance, and track the run

- Set and record seeds (Python, NumPy, and the framework). Default `--seed 42`.
- Record provenance with the **same interpreter that runs training**, so package versions are the real ones:

  ```bash
  <project-python> "${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py" --data <data> --seed <seed> \
    --split-manifest <out-dir>/splits/split-manifest.json --out <out-dir>/provenance-train.json
  ```

  It is standard-library only. Run it with the project's interpreter (`python`, `uv run python`, `.venv/bin/python`, or `conda run python`), not `uv run provenance.py`: that would create an isolated environment and report the wrong package versions. If it is unavailable (another agent harness), record the git SHA and dirty flag, the Python and key package versions, lockfile hashes, and the data file's sha256 by hand.
- If the project already uses MLflow or W&B (imports, `MLFLOW_TRACKING_URI` / `WANDB_PROJECT`, or a note in the settings file), make sure the run logs parameters, metrics, the provenance file, and the model artifact there, and record the run URL in `tracking_url`. Do not install or configure a tracker without asking; otherwise the artifact and `<out-dir>/train-metrics.json` are the record.

### 5. Launch training

- Run the (possibly modified) training command
- Capture the PID or process handle
- Log the exact command that was executed to `<out-dir>/run-command.txt`
- Confirm the process starts successfully (no immediate crash within the first 10 seconds)

Short tabular runs (seconds to minutes) can run in the foreground; skip step 6 for them.

### 6. Delegate monitoring to babysit-training

Hand off to `babysit-training` immediately after the process is confirmed running:

- Pass the training log path or PID to `babysit-training`
- Forward `--interval`, `--max-interval`, `--no-backoff`, `--no-fix` flags if provided
- Pass `--out-dir <out-dir>` and `--run-id <run_id>` so the monitoring artifact lands in the shared directory

`babysit-training` runs until the process reaches a terminal state. Resume control once it exits.

### 7. Use native early stopping

Configure early stopping in the training framework before launch, monitoring `--early-stop-metric` on `val` with `--early-stop-patience`:

- HF Trainer: `EarlyStoppingCallback` with `load_best_model_at_end=True` and `metric_for_best_model`
- Lightning: `EarlyStopping` callback; Keras: `EarlyStopping`
- LightGBM / XGBoost: early-stopping rounds on the `val` set
- scikit-learn `HistGradientBoosting*`: `early_stopping=True`

If the training code has no early-stopping hook, propose the code change and wait for approval. Do not stop a running job from outside: that is a cancellation, which needs approval. Record `triggered`, the best iteration, and the best value from the framework's own state (e.g. `trainer_state.json`, `booster.best_iteration`).

### 8. Hyperparameter sweeps (`--sweep`)

Run the search space from `plan-experiment.json` with Optuna (`uv run --with optuna`) before the final training run:

- Sampler and pruning: TPE sampler with a fixed seed, and a median or Hyperband pruner, so weak trials stop early.
- Objective: the primary metric on `val`, or cross-validation inside `train`+`val` matching the split strategy. **Never `test`.**
- Budget: stop at the plan's trial count and time box. A sweep that would exceed the plan's budget needs approval.
- Log each trial to the tracker (or `<out-dir>/sweep/trials.csv`).
- Train the final model with the best parameters.
- Report the trial count, the best value (with CV std when used), and the best parameters in `sweep`.

### 9. Checkpoint management

- Scan `--checkpoint-dir` for checkpoints after training terminates
- Identify the **best checkpoint** by the `val` metric (`--early-stop-metric` if set); otherwise use the most recent
- Record all checkpoints found with step numbers and metric values in the artifact
- Log the best checkpoint path: `Best checkpoint: <path> (step <N>, <metric>=<val>)`

### 10. Failure recovery

If `babysit-training` returns `NO-GO` (terminal state `FAILED` or `CANCELLED`):

- Automatically invoke `check-failed-run` with the training log and `--out-dir`
- Surface the root cause and approved recovery actions in the terminal summary
- Do **not** auto-apply high-risk fixes (hyperparameter changes, checkpoint rollbacks) — surface them as `needs-approval` actions

### 11. Terminal summary

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
Pre-flight: <n passed>/<n run> (<failed checks or none>)
Sweep: <n trials, best value, or not run>
Provenance: <out-dir>/provenance-train.json (git <sha><-dirty>)
Tracking: <run URL or none>

Decision: GO | NO-GO
Confidence: high | medium | low
```

`GO`: terminal state is `SUCCEEDED` or `EARLY_STOPPED` with no unresolved critical anomalies.
`NO-GO`: terminal state is `FAILED`, `CANCELLED`, or `TIMEOUT` with unresolved blockers.

### Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- the training command, as a note in a fenced block
- pre-flight checks: `exec` the cheap ones (sample fit, constant-prediction check)
- **reproducibility**: when training takes under about a minute (e.g. `train_tabular.py`), `exec` the same command with `--out-dir "$(mktemp -d)"` and print the validation and CV metric lines, so verify retrains from scratch. Otherwise `exec` the sha256 of the model or checkpoint and the predictions files, and print the key fields of `train-metrics.json`
- the training data hash: `exec` a sha256 of the data file (a Python `hashlib` one-liner works on macOS and Linux)

### JSON artifact

Write `train-model.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` when training succeeded or early-stopped without blockers; `NO-GO` on failure
- `train_cmd`, `hyperparameters`, `terminal_state`, `total_steps`, `total_epochs`
- `early_stopping`: `enabled`, `metric`, `patience`, `triggered`, `triggered_at_step`
- `final_metrics`, `best_checkpoint`, `all_checkpoints`
- `training_duration_seconds`, `babysit_training_ref`
- `seed`, `preflight`, `sweep`, `provenance_path`, `tracking_url`
- `provenance`: the contents of `provenance-train.json`

## Example session

```
/agentic-ml:train-model uv run train.py --config configs/gpt2-base.yaml --hp lr=3e-4 --hp batch_size=16 --early-stop-metric eval_loss --early-stop-patience 3 --checkpoint-dir ./checkpoints --out-dir ./reports/run-001

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

- [scripts/train_tabular.py](scripts/train_tabular.py) — leakage-safe tabular training scaffold (`train` / `predict`)
- [references/preflight-checks.md](references/preflight-checks.md) — pre-flight check recipes by framework
- [babysit-training](../babysit-training/SKILL.md) — continuous monitoring skill (invoked internally)
- [check-failed-run](../check-failed-run/SKILL.md) — failure diagnosis skill (invoked on NO-GO)
- [../../references/schemas.md](../../references/schemas.md) — JSON artifact schema
- [../../references/vocabulary.md](../../references/vocabulary.md) — canonical enum values
