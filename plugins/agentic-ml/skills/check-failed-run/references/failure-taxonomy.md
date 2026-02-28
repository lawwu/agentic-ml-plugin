# Failure Taxonomy

Reference for the `debug-training` skill. A catalog of failure modes with signals, severity, and initial triage guidance.

---

## nan-inf — NaN or Inf Loss/Gradients

**Severity**: Critical

**Signals**:

- `loss=nan`, `loss=inf`, `loss=NaN` in log output
- `grad_norm=inf`
- `FP16 scaler reduced to 0` or AMP overflow warnings
- Weights become `nan` (model outputs garbage on subsequent steps)

**When it appears**:

- Within first 50 steps → lr too high, normalization missing, bad data
- After many stable steps → gradient explosion (precursor: grad_norm spike 2–5 steps earlier)
- After precision change → fp16/bf16 overflow in mixed precision

**Framework-specific signals**:

- HF Trainer: `AMP: loss scale reached minimum` or `grad scaler state`
- Lightning: `detected nan in loss`
- DeepSpeed: `overflow detected, setting skip_step=True`

**Severity**: Critical — training cannot continue without a fix.

---

## oom — Out of Memory

**Severity**: Critical

**Signals**:

- `CUDA out of memory. Tried to allocate ...`
- `torch.cuda.OutOfMemoryError`
- `RuntimeError: CUDA error: out of memory`
- OOM killer messages in `dmesg` or `journalctl` (host RAM OOM)
- Process exits with signal 9 (SIGKILL) without traceback

**When it appears**:

- At training start → model too large for configured batch size
- At validation start → eval batch size inherits train batch size
- After stable training → memory leak (e.g., accumulating tensors in Python list)
- After checkpoint save → checkpoint remains in memory

**Framework-specific signals**:

- FSDP: OOM during parameter all-gather
- DeepSpeed: OOM in optimizer states or activation checkpointing failure
- Lightning: OOM logged as `RuntimeError` in trainer loop

**Severity**: Critical — process cannot continue without memory reduction.

---

## nccl-distributed — Distributed Runtime Failure

**Severity**: Critical

**Signals**:

- `NCCL error in: ...`, `ncclInternalError`
- `Gloo` socket timeout errors
- `ProcessGroupNCCL: Timeout`
- `RuntimeError: Function AddmmBackward0 ... expected all tensors to be on the same device`
- Hang with no log output across all ranks
- One rank crashes silently (others hang waiting for it)

**When it appears**:

- At startup → NCCL misconfiguration, wrong `MASTER_ADDR`/`MASTER_PORT`
- During backward pass → rank mismatch or asymmetric forward pass
- During checkpoint sync → one worker fails, others hang

**Framework-specific signals**:

- `torchrun`: `rendezvous` failure at startup
- Lightning: `Detected rank 0 exit with non-zero exit code`
- DeepSpeed: `[deepspeed] NCCL all-reduce failed`

**Severity**: Critical — requires kill and restart of all workers.

---

## cuda-runtime — CUDA Runtime Error

**Severity**: Critical

**Signals**:

- `CUDA error: device-side assert triggered`
- `CUDA error: an illegal memory access was encountered`
- `CUDA error: invalid device function` (kernel compiled for wrong GPU arch)
- `AssertionError` deep in CUDA kernels
- Segmentation fault with CUDA stack trace

**When it appears**:

- `device-side assert`: label index out of range (num_classes mismatch), invalid attention mask
- `illegal memory access`: tensor shape mismatch in custom CUDA kernel
- `invalid device function`: model compiled for CUDA arch not supported by this GPU

**Severity**: Critical — hard crash, usually requires script restart.

---

## data-pipeline — Data Pipeline Failure

**Severity**: High–Critical

**Signals**:

- `RuntimeError: Expected ... got shape ...` (shape mismatch in forward pass)
- `ValueError: Expected input batch_size ... to match target batch_size ...`
- `IndexError` or `KeyError` in `__getitem__`
- Corrupt file warnings (`PIL.UnidentifiedImageError`, `pyarrow.lib.ArrowInvalid`)
- Silent: loss spikes periodically → bad batch with extreme values, not an error

**When it appears**:

- Random timing → corrupt samples in dataset (non-deterministic order)
- After resuming → batch size or num_workers changed between runs
- At specific steps → dataset exhausted with `drop_last=False`

**Severity**: High — training can continue but data integrity is compromised.

---

## config-error — Configuration Error

**Severity**: High

**Signals**:

- `KeyError: 'hidden_size'` or similar on model/trainer init
- `AttributeError: 'TrainingArguments' object has no attribute ...`
- `TypeError: __init__() got an unexpected keyword argument`
- `FileNotFoundError` for dataset, checkpoint, or tokenizer path
- Wrong `num_labels` → silent label mismatch causing nonsense outputs

**When it appears**:

- At startup → always; config errors crash before training begins
- After library upgrade → API change in HF Transformers, Lightning, DeepSpeed

**Severity**: High — blocks training start; usually easy to fix.

---

## io-checkpoint — I/O and Checkpoint Errors

**Severity**: Medium–High

**Signals**:

- `OSError: [Errno 28] No space left on device`
- `PermissionError: [Errno 13] Permission denied`
- `FileNotFoundError` when loading checkpoint on resume
- `RuntimeError: PytorchStreamReader failed reading zip archive`
- NFS/GCS timeouts during checkpoint save

**When it appears**:

- Periodically → checkpoint save failing silently, then crash on next resume
- After long training → disk fills up incrementally

**Severity**: Medium if training continues; High if resume is blocked.

---

## optimization-divergence — Optimization Divergence

**Severity**: High

**Signals**:

- Loss increases monotonically over 10+ steps (not NaN — just getting worse)
- Validation loss diverges while train loss remains stable (overfitting or leakage)
- Learning rate schedule misconfigured (warmup too short, no decay, cosine restarts)
- Gradient norm steadily increasing (not explosion — just drifting up)

**When it appears**:

- Early training → lr too high or warmup too short
- Mid-training → lr schedule issues, wrong optimizer for task
- Late training → lr not annealed, model has fit noise

**Severity**: High — training produces a poor model; no hard crash.

---

## stalled — Stalled Training

**Severity**: High

**Signals**:

- No new log lines for multiple polling intervals
- Step count not advancing
- Process is alive (`ps -p <pid>` returns), GPU utilization: 0%
- `D` state in `ps aux` (uninterruptible sleep — usually I/O wait)
- NCCL watchdog timeout not yet triggered

**When it appears**:

- During checkpoint save → slow NFS or storage contention
- During data loading → all workers blocked on I/O
- In distributed training → one rank waiting for another that is stuck

**Severity**: High — training is not making progress; may self-resolve or require kill.

---

## process-crash — Unexpected Process Crash

**Severity**: Critical

**Signals**:

- PID no longer alive, log ends abruptly (no "training complete" message)
- `Killed` in log (OOM killer)
- Segfault (`Segmentation fault (core dumped)`)
- SLURM/LSF: `CANCELLED at ... due to TIME_LIMIT` or `NODE_FAIL`
- Exit code: non-zero (check with `echo $?` or scheduler logs)

**When it appears**:

- During backward pass → OOM, segfault in custom CUDA kernel
- During checkpoint → disk full causing partial write and then crash
- On scheduler timeout → job wall time exceeded

**Severity**: Critical — requires diagnosis before restart.
