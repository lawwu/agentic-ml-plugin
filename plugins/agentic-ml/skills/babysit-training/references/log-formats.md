# Training Log Formats

Reference for the `babysit-training` skill. Use this to parse metrics from logs.

---

## Hugging Face Transformers (Trainer)

Default format (JSON-like, printed to stdout):

```
{'loss': 2.3415, 'grad_norm': 0.8721, 'learning_rate': 0.0003, 'epoch': 1.24}
{'loss': 2.2891, 'grad_norm': 0.9102, 'learning_rate': 0.0002987, 'epoch': 1.25}
```

Progress bar format (tqdm):
```
  12%|████▌                                | 1200/10000 [08:21<1:00:23, 2.43it/s]
```

**Extraction**:
- Parse JSON-like dicts for `loss`, `grad_norm`, `learning_rate`, `epoch`
- For step count, parse `it/s` and progress bar or look for `step` key

---

## PyTorch Lightning

Default format:
```
Epoch 1:  12%|███▌              | 120/1000 [00:45<05:32, 2.65it/s, v_num=0, train_loss=2.34]
```

Or with explicit logging:
```
[2024-01-15 10:03:21,451][INFO] - Epoch 1, step 120: train_loss=2.341 val_loss=2.891
```

**Extraction**: parse `train_loss`, `val_loss`, epoch/step from tqdm bar or structured log lines.

---

## PyTorch (manual training loop)

Varies by codebase. Common patterns:

```
Epoch [1/10], Step [100/5000], Loss: 2.3415, LR: 3.00e-04
```

```
step=100 loss=2.3415 lr=0.0003 grad_norm=0.872 tokens_per_sec=142000
```

```json
{"step": 100, "loss": 2.3415, "lr": 0.0003, "grad_norm": 0.872, "elapsed": 45.2}
```

**Extraction**: look for key=value pairs or JSON objects. The first line of the log often shows config.

---

## TensorFlow / Keras

```
Epoch 1/10
1000/1000 [==============================] - 45s 45ms/step - loss: 2.3415 - accuracy: 0.4821
```

Or:
```
Step 100: loss = 2.3415
```

**Extraction**: parse `loss`, `accuracy`, `val_loss`, `val_accuracy` from Keras output.

---

## JAX / Flax (with Orbax or custom)

Typically custom structured logs:
```
step 100: loss=2.341, lr=0.0003, grad_norm=0.87, steps/sec=12.3
```

Or JSON:
```json
{"step": 100, "metrics": {"loss": 2.341, "accuracy": 0.483}, "lr": 0.0003}
```

---

## SLURM / Cluster Jobs

Logs are typically in `slurm-<jobid>.out`. The training log may be mixed with SLURM system messages:

```
srun: Job step aborted: Waiting up to 62 seconds for job step to finish.
```

Watch for SLURM signals:
- `PREEMPTION` — job was preempted
- `TIME LIMIT` — approaching wall time
- `Killed` — OOM killer or SIGKILL

Also check `squeue -j <jobid>` to see job state.

---

## Weights & Biases (W&B)

W&B itself doesn't write a training log; it uploads metrics via the SDK. To monitor:
- Use `wandb` CLI: `wandb sync --sync-all` or query the API
- Or tail the local wandb run dir: `~/.wandb/` or `./wandb/run-*/logs/debug.log`

The debug log contains raw metric uploads.

---

## General heuristics for unknown formats

1. Print first 20 lines to identify format
2. Look for recurring patterns with numbers after `=` or `:`
3. Look for keywords: `loss`, `step`, `epoch`, `iter`, `accuracy`, `perplexity`
4. If JSON lines: use `jq` to extract fields
5. If mixed: isolate metric lines with `grep -E 'loss|step|epoch'`
