# Root Cause Patterns

Reference for the `debug-training` skill. Per-failure diagnosis procedures, log patterns, and framework-specific config checks.

---

## nan-inf

### Diagnosis procedure

1. Find the first step with NaN loss — scan backward 5–10 steps
2. Check `grad_norm` trend: did it spike before the NaN? (gradient explosion)
3. Check for AMP overflow warnings in the 10 steps before NaN
4. Check for data loading warnings or errors near that step
5. Check `loss_scale` value (fp16 only): if it hit minimum, overflows were occurring silently

### Log patterns

```
# Gradient explosion preceding NaN
step 441: grad_norm=1.2 → step 442: grad_norm=4812.3 → step 443: loss=nan

# AMP overflow (HF Trainer)
Grad overflow on iteration 442, skipping update

# AMP overflow (PyTorch native)
[W TensorIteratorBase.cpp] ...amp autocast overflow
```

### Framework-specific configs to check

**HF Trainer (`TrainingArguments`)**:

- `fp16=True` + no `fp16_opt_level` → default "O1" which can overflow; try `bf16=True`
- `max_grad_norm=None` → no clipping; set `max_grad_norm=1.0`
- `dataloader_num_workers=0` → ensures bad batch reproducibility for debugging

**Lightning**:

- `precision="16-mixed"` → try `"bf16-mixed"`
- `gradient_clip_val=None` → set to `1.0`
- Check `on_before_optimizer_step` hook for custom grad manipulation

**DeepSpeed**:

- `"fp16": {"enabled": true, "loss_scale": 0}` → dynamic loss scaling; if `loss_scale_window` is too small, scaling collapses too fast
- `"bf16": {"enabled": true}` → more stable; try switching
- `"gradient_clipping": 1.0` must be set in DeepSpeed config, not Trainer args

**FSDP**:

- Mixed precision policy: `param_dtype=torch.float16` can overflow; use `bfloat16`
- Ensure `mixed_precision.reduce_dtype` matches `param_dtype`

---

## oom

### Diagnosis procedure

1. Run `nvidia-smi` to capture current VRAM allocation
2. Check if OOM occurred at eval start (eval inherits train batch size)
3. Check if the model is storing unnecessary tensors (e.g., collecting outputs in a list)
4. Check if activation checkpointing is enabled — if not, enable it for large models
5. Check `torch.cuda.memory_summary()` output if available in logs

### Log patterns

```
# PyTorch OOM
RuntimeError: CUDA out of memory. Tried to allocate 2.00 GiB
  (GPU 0; 79.20 GiB total capacity; 74.82 GiB already allocated)

# OOM killer (host RAM)
Killed
# or in dmesg:
Out of memory: Kill process 48291 (python) score 800

# FSDP OOM during all-gather
RuntimeError: CUDA out of memory. Tried to allocate ...
  during all_gather_into_tensor (FSDP parameter sharding)
```

### Framework-specific configs to check

**HF Trainer**:

- `per_device_eval_batch_size` — defaults to `per_device_train_batch_size`; set separately
- `gradient_checkpointing=True` — enables activation checkpointing
- `dataloader_pin_memory=True` with large batches can exacerbate host OOM

**Lightning**:

- `accumulate_grad_batches` — check if effective batch is larger than expected
- Enable: `trainer = Trainer(enable_progress_bar=True, precision="16-mixed")`

**DeepSpeed**:

- `"zero_optimization": {"stage": 3}` — most memory-efficient; try upgrading from stage 1/2
- `"offload_optimizer": {"device": "cpu"}` — offload optimizer states to CPU RAM
- `"offload_param": {"device": "cpu"}` — offload model params (slowest but most memory savings)

**FSDP**:

- `ShardingStrategy.FULL_SHARD` — most memory efficient
- `cpu_offload=CPUOffload(offload_params=True)` — CPU offload

---

## nccl-distributed

### Diagnosis procedure

1. Check if all ranks have logs or only some — silent rank crash causes others to hang
2. Look for `NCCL WARN` or `NCCL INFO` messages in each rank's log
3. Check `NCCL_TIMEOUT` env var — default 1800s; may need to increase for large all-reduces
4. Check `MASTER_ADDR` and `MASTER_PORT` env vars are consistent across all workers
5. Verify `NCCL_IB_DISABLE=1` if InfiniBand is unavailable (common on cloud instances)

### Log patterns

```
# NCCL timeout
ProcessGroupNCCL: Timeout at NCCL_TIMEOUT=1800s
  Some NCCL collective (allreduce) did not complete in time.

# Rank mismatch
RuntimeError: Mismatch in number of participants ...

# Gloo timeout (CPU collectives)
Gloo connectFullMesh failed with [workers]: ... connection timed out
```

### Environment variables to check

```bash
# Required for multi-node
echo $MASTER_ADDR   # Should be rank-0 IP, reachable by all workers
echo $MASTER_PORT   # Should be open and unused
echo $WORLD_SIZE    # Must match number of GPUs × nodes
echo $RANK          # Unique per worker

# NCCL tuning
echo $NCCL_DEBUG    # Set to INFO for verbose NCCL logs
echo $NCCL_TIMEOUT  # Seconds; increase for large models
```

---

## cuda-runtime

### Diagnosis procedure

1. `CUDA_LAUNCH_BLOCKING=1` — run with this env var to get synchronous error messages with real stack traces
2. Check label shape and range: `assert labels.max() < num_classes`
3. Check attention mask values: should be in `{0, 1}` not floats
4. For `invalid device function`: check `torch.cuda.get_device_capability()` vs compiled CUDA arch

### Log patterns

```
# Device-side assert (most common: label out of range)
RuntimeError: CUDA error: device-side assert triggered
CUDA kernel errors might be asynchronously reported at some other API call

# Illegal memory access
RuntimeError: CUDA error: an illegal memory access was encountered

# Wrong CUDA arch
RuntimeError: CUDA error: invalid device function
```

### Debugging approach

```bash
# Run with synchronous CUDA errors for real stack traces
CUDA_LAUNCH_BLOCKING=1 uv run python train.py ...

# After fixing, remove for performance
```

---

## data-pipeline

### Diagnosis procedure

1. Reproduce the error with `--num_workers 0` (disables multiprocessing for easier debugging)
2. Iterate over the DataLoader manually for a few batches to find the failing sample
3. Check if the error is deterministic (same step each run) or random
4. For shape errors: print batch shapes in the training loop before the forward pass

### Log patterns

```
# Shape mismatch
RuntimeError: Expected input batch_size (16) to match target batch_size (14)

# DataLoader worker crash (silent)
ERROR: Caught IndexError in DataLoader worker process 2
  File "dataset.py", line 84, in __getitem__

# Corrupt sample (PIL)
PIL.UnidentifiedImageError: cannot identify image file
```

### Debugging snippet

```python
# Add to training loop for diagnosis
for i, batch in enumerate(train_loader):
    print(f"Batch {i}: {batch['input_ids'].shape}, labels={batch['labels'].shape}")
    if i > 5: break
```

---

## config-error

### Diagnosis procedure

1. Read the full traceback — config errors always have a clean stack trace at startup
2. Check library versions: `uv pip show transformers torch lightning deepspeed`
3. Check if the checkpoint was saved with a different library version
4. Search for the exact argument name in the current library's docs

### Log patterns

```
# Wrong argument name (library version change)
TypeError: TrainingArguments.__init__() got an unexpected keyword argument 'fp16_backend'

# Wrong num_labels
ValueError: Expected input batch_size to match target ...
  (often a symptom of wrong num_labels causing wrong output shape)

# Missing file
FileNotFoundError: [Errno 2] No such file or directory: './checkpoint/config.json'
```

---

## io-checkpoint

### Diagnosis procedure

1. `df -h <checkpoint_dir>` — check disk space
2. `ls -la <checkpoint_dir>` — check permissions and partial checkpoint files
3. For NFS: `stat <checkpoint_dir>` to check if mount is responsive
4. Check for partial `.tmp` files that indicate a failed write

### Log patterns

```
# Disk full
OSError: [Errno 28] No space left on device: '/mnt/runs/checkpoint-1200'

# Permission denied
PermissionError: [Errno 13] Permission denied: '/shared/checkpoints/model.safetensors'

# Corrupt checkpoint (partial write)
RuntimeError: PytorchStreamReader failed reading zip archive: failed finding central directory
```

---

## optimization-divergence

### Diagnosis procedure

1. Plot loss curve: is it monotonically increasing or oscillating wildly?
2. Extract lr at the diverging step: `grep "lr=" train.log | tail -20`
3. Check the lr schedule configuration — warmup steps, total steps, scheduler type
4. Check if optimizer state was loaded from a checkpoint with a different lr

### Framework-specific configs to check

**HF Trainer**:

- `lr_scheduler_type` — default is `linear`; check if cosine or polynomial was intended
- `warmup_steps` vs `warmup_ratio` — only one should be set
- `learning_rate` — verify it matches the paper/baseline (common typo: `3e-4` vs `3e-5`)

**Lightning**:

- `configure_optimizers()` return value — must return `(optimizers, schedulers)` correctly
- `scheduler.step()` frequency — `interval: "step"` vs `interval: "epoch"`

---

## stalled

### Diagnosis procedure

1. `ps -p <pid>` — is the process alive?
2. `nvidia-smi` — is GPU utilization near 0%?
3. `ps aux | grep -E "uv run|python"` — is the process in `D` state (uninterruptible I/O wait)?
4. `lsof -p <pid> | grep .parquet` — is it blocked reading a specific file?
5. For distributed: check if one rank is alive and others are all waiting

### Log patterns

```
# No new lines — only absence of output indicates stall
# Check with:
tail -f train.log  # no new output for 5+ minutes

# NCCL watchdog (if enabled)
Timeout waiting for other ranks, NCCL watchdog: 300s
```
