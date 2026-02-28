# Common Training Issues and Fix Strategies

Reference for the `babysit-training` skill. Use this when an anomaly is detected.

---

## NaN / Inf Loss

**Signals**: `loss=nan`, `loss=inf`, `loss=NaN` in log output.

**Root causes** (most common first):
1. Gradient explosion — grad norm spikes before NaN appears
2. Bad data batch — a corrupted sample produces extreme activations
3. Numerical instability — e.g., log(0), division by zero in custom loss
4. Learning rate too high — especially with no warmup

**Diagnosis steps**:
1. Scroll back 5–10 steps before the NaN and check grad_norm trend
2. Check if any data loading warnings precede the NaN
3. Check if mixed precision (`fp16`/`bf16`) is enabled — NaN is more common with fp16

**Fix strategies**:
- If grad explosion: suggest reducing lr by 10×, adding gradient clipping (`max_norm=1.0`)
- If recent checkpoint exists (<5 min ago): offer to roll back
- If custom loss: flag for user review — do not auto-fix
- Never auto-modify hyperparameters; always ask user

---

## Loss Divergence

**Signals**: Loss increases monotonically over 5+ consecutive logged steps.

**Diagnosis**:
1. Compare current loss to baseline (first 10 steps of this run)
2. Check lr schedule — is lr rising (e.g., warmup misconfigured)?
3. Check if dataset shuffling is disabled (could be a pathological batch sequence)

**Fix strategies**:
- Flag to user with trend data; do not auto-fix
- Suggest: reduce lr, check lr scheduler config, inspect recent batches

---

## Stalled Training (No Progress)

**Signals**: No new log lines for 2+ polling intervals; step count does not advance.

**Diagnosis**:
1. Check if process is still alive: `ps -p <pid>` or `pgrep <name>`
2. Check system load: `uptime`, `nvidia-smi` for GPU utilization
3. Check for deadlock indicators: `D` state in `ps`, NCCL timeouts in logs
4. Check disk space: `df -h` — disk full can stall checkpoint saves

**Fix strategies**:
- If process dead: attempt restart (safe if command is known)
- If NCCL/distributed deadlock: flag to user — typically requires kill + restart
- If disk full: alert user immediately, do not auto-delete files

---

## CUDA Out of Memory (OOM)

**Signals**: `CUDA out of memory`, `RuntimeError: CUDA`, `torch.cuda.OutOfMemoryError`

**Diagnosis**:
1. Run `nvidia-smi` to see current VRAM usage
2. Check if batch size or sequence length was recently increased
3. Check if gradient accumulation is configured correctly

**Fix strategies** (all require user approval):
- Reduce batch size
- Enable gradient checkpointing
- Switch from fp32 to bf16/fp16
- Increase `--gradient-accumulation-steps`

Safe auto-action: run `nvidia-smi` and report VRAM stats to user.

---

## Gradient Explosion

**Signals**: `grad_norm` >> baseline (e.g., > 1000, or > 100× the average of the last 20 steps)

**Note**: Often precedes NaN loss. Treat as a leading indicator.

**Diagnosis**:
1. Check if gradient clipping is enabled (`max_norm` in optimizer/trainer config)
2. Check if lr recently increased (scheduler or manual change)
3. Look for data loading warnings before the spike

**Fix strategies**:
- If no clipping configured: strongly recommend adding it (user must approve)
- If clipping configured but explosion still occurs: lr likely too high

---

## Process Crash

**Signals**: Process PID is no longer alive; log ends abruptly without a "training complete" message.

**Diagnosis**:
1. Check last lines of log for error message or traceback
2. Check system logs: `journalctl -n 50` or `dmesg | tail -20` for OOM killer activity
3. Check exit code if available

**Fix strategies**:
- If OOM killer: reduce memory usage (see OOM section)
- If Python exception: report traceback to user; do not auto-restart without understanding cause
- If clean exit but unexpected: check if job was killed by scheduler (SLURM, etc.)

---

## Checkpoint Save Failure

**Signals**: `Error saving checkpoint`, `OSError`, `disk quota exceeded` during checkpoint

**Diagnosis**:
1. Check disk space: `df -h` on the checkpoint directory
2. Check file permissions on the output directory
3. Check if NFS mount is responsive (for remote mounts)

**Fix strategies**:
- If disk full: alert user immediately; list largest files in output dir
- If permissions: alert user
- Never delete existing checkpoints to make space

---

## Slow Throughput

**Signals**: Samples/sec or steps/sec drops > 50% from the baseline established in the first 5 polls.

**Diagnosis**:
1. Check GPU utilization: `nvidia-smi`
2. Check CPU/IO wait: `iostat -x 1 3` or `top`
3. Check if data loading is the bottleneck (CPU near 100%, GPU low)
4. Check for thermal throttling on remote machines: `nvidia-smi -q -d TEMPERATURE`

**Fix strategies**:
- Flag to user with utilization stats
- If data loading bottleneck: suggest increasing `num_workers`, prefetching, or using faster storage
- Do not auto-tune training parameters
