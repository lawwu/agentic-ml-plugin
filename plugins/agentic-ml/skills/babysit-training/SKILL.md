---
name: babysit-training
description: Continuously monitors a machine learning training run (local, remote, or cloud) until it completes or hits a critical issue. Supports local log files, SSH targets, process names, Vertex AI Pipeline jobs, and Vertex AI Custom training jobs. Run this automatically whenever a training job is started or handed off — poll for anomalies, report progress, and escalate issues without waiting to be asked.
argument-hint: "[log-file | user@host:path | --pid PID | --proc NAME | --vertex-pipeline JOB | --vertex-training JOB] [--project PROJECT] [--region REGION] [--interval SECONDS]"
---

# Check Training

Monitor a machine learning training run and maintain session control until it reaches a terminal state.

## Invocation

Arguments ($ARGUMENTS) are interpreted as:

- **Local log file**: a path like `./logs/train.log` or `/tmp/run.log`
- **Remote log file**: `user@host:/path/to/train.log` (uses SSH)
- **Process by PID**: `--pid 12345`
- **Process by name**: `--proc torchrun`, `--proc train.py`, or `--proc "uv run"`
- **Vertex AI Pipeline job**: `--vertex-pipeline JOB_ID_OR_NAME` (KFP/Vertex Pipelines)
- **Vertex AI Custom training job**: `--vertex-training JOB_ID_OR_NAME`
- **Wandb/MLflow run**: `--wandb run-id` or `--mlflow run-id`

Optional flags:

- `--project PROJECT` — GCP project ID (required for Vertex AI targets; falls back to `gcloud config get-value project`)
- `--region REGION` — GCP region (default: `us-central1`)
- `--interval N` — initial poll interval in seconds (default: 30; default 60 for Vertex AI)
- `--max-interval N` — cap for exponential backoff in seconds (default: 300)
- `--no-backoff` — disable exponential backoff; poll at fixed `--interval`
- `--once` — take a single snapshot and exit
- `--no-fix` — observe only, never attempt fixes

Target: $ARGUMENTS

## Your responsibilities

### 1. Parse the target

Determine whether the target is local, remote, or cloud, and what monitoring strategy to use:

- **Log file (local)**: `tail -n 100 <path>` to read recent lines
- **Log file (remote)**: `ssh user@host 'tail -n 100 <path>'` to read recent lines
- **PID**: `ps -p <pid>` to check if process is alive; read `/proc/<pid>/fd` or companion log if available
- **Process name**: `pgrep -a <name>` to find PIDs, then follow above
- **Vertex AI Pipeline**: use `gcloud` CLI or Python SDK — see [references/vertex-ai.md](references/vertex-ai.md)
- **Vertex AI Custom training**: use `gcloud ai custom-jobs describe` — see [references/vertex-ai.md](references/vertex-ai.md)
- **No argument given**: ask the user for the target before proceeding

### 2. Establish a baseline

On first poll:

- Confirm the process is running and the log is readable
- Extract the current epoch/step/iteration number
- Note the current loss and any other reported metrics (accuracy, perplexity, grad norm, lr, etc.)
- Identify the log format (structured JSON, key=value pairs, plain text) — see [references/log-formats.md](references/log-formats.md)
- Report a one-line status: `[Step X/Y] loss=Z, lr=A, gpu_util=B%`

### 3. Continuous monitoring loop

Maintain a current interval starting at `--interval`. Unless `--no-backoff` is set, apply exponential backoff:

- **After each uneventful poll** (no anomaly, loss delta ≤5%, no new epoch/stage, no Vertex AI state change): multiply current interval by 1.5, capped at `--max-interval`
- **Reset to `--interval`** whenever any of the following occurs:
  - An anomaly is detected (any severity)
  - Loss delta > 5% since the previous poll
  - A new epoch or training stage begins
  - Vertex AI pipeline task state or job state changes

Poll on each interval. For each poll:

1. Read the latest log lines (or query the metrics API)
2. Extract the latest step/epoch and metrics
3. Run anomaly checks (see [references/common-issues.md](references/common-issues.md))
4. If anomalies are found, diagnose and decide whether to fix or escalate; reset interval to `--interval`
5. Report a one-line progress update (include `next poll in Xs` — see Section 6)
6. Update the current interval per backoff rules above
7. Check for terminal conditions (see Stop Conditions below)

After any fix that pushes a change or restarts a process, restart the monitoring loop in the **same turn** — do not wait for the user to re-invoke.

### 4. Anomaly detection

**For local/remote training runs**, check on every poll:

| Issue | Signal | Severity |
|---|---|---|
| NaN/Inf loss | `loss=nan` or `loss=inf` in logs | Critical |
| Loss divergence | Loss increases monotonically over 5+ steps | High |
| Stalled training | No new log lines for 2+ intervals | High |
| OOM / CUDA error | `CUDA out of memory` or `RuntimeError` in logs | Critical |
| Gradient explosion | Grad norm > 1000 (or >> baseline) | High |
| Process crash | PID no longer alive | Critical |
| Checkpoint save failure | `Error saving checkpoint` | Medium |
| Slow throughput | Samples/sec drops > 50% from baseline | Medium |

**For Vertex AI Pipeline jobs**, check on every poll:

| Issue | Signal | Severity |
|---|---|---|
| Pipeline failure | `state: PIPELINE_STATE_FAILED` | Critical |
| Task failure | Any task in `TASK_STATE_FAILED` state | High |
| Pipeline cancellation | `state: PIPELINE_STATE_CANCELLED` | High |
| Stuck pipeline | State remains `PIPELINE_STATE_RUNNING` with no task state changes for 3+ intervals | High |
| Error in task logs | Error-level messages in `pipeline_job_task_events` log | Medium |

**For Vertex AI Custom training jobs**, check on every poll:

| Issue | Signal | Severity |
|---|---|---|
| Job failure | `state: JOB_STATE_FAILED` | Critical |
| Job cancellation | `state: JOB_STATE_CANCELLED` | High |
| Stalled job | State remains `JOB_STATE_RUNNING` with no log output for 3+ intervals | High |
| OOM / CUDA error | Errors in Cloud Logging for the job | Critical |

For local/remote anomaly details and fix strategies, see [references/common-issues.md](references/common-issues.md).
For Vertex AI-specific monitoring, see [references/vertex-ai.md](references/vertex-ai.md).

### 5. Fix policy

Apply fixes only when:

- The fix is clearly safe and reversible
- `--no-fix` flag is NOT set
- You have not already retried this type of fix 3 times

Safe fixes you may attempt:

- Restart a crashed process (if restart command is determinable from the log header or working directory)
- Clear CUDA cache (`torch.cuda.empty_cache()` via a helper script if accessible)
- Kill and restart a zombie process

Fixes that require user approval:

- Changing hyperparameters (learning rate, batch size)
- Rolling back to a checkpoint
- Canceling the run

Always state what you are about to do before doing it.

### 6. Progress reporting format

**Local/remote training:**

```
[HH:MM:SS] Step 1200/10000 (12%) | loss=0.342 | lr=1e-4 | grad_norm=0.8 | 142 samples/s
  GPU: 94% util, 18.2/24 GB VRAM | ETA: ~1h 23m | next poll in 45s
```

If remote SSH, prefix with `[user@host]`.

**Vertex AI Pipeline job:**

```
[HH:MM:SS] Pipeline: my-training-pipeline (projects/my-proj/locations/us-central1/pipelineJobs/123)
  State: RUNNING | Elapsed: 1h 23m
  Tasks: 3 SUCCEEDED, 1 RUNNING (data-preprocessing), 2 PENDING
  Running task: model-training — started 45m ago
```

**Vertex AI Custom training job:**

```
[HH:MM:SS] Custom job: my-gpt2-finetune (projects/my-proj/locations/us-central1/customJobs/456)
  State: RUNNING | Elapsed: 2h 10m | Worker: n1-standard-8 + 4x T4
  Recent logs: Step 4200/10000 | loss=0.842
```

Report a full summary every 5 polls or when something notable happens.

### 7. Stop conditions

Stop monitoring and hand back control to the user when:

- **Training complete**: log indicates run finished (`Training finished`, `Epoch N/N done`, process exits cleanly)
- **Vertex AI terminal state**: pipeline or job reaches `SUCCEEDED`, `FAILED`, or `CANCELLED`
- **Critical unrecoverable error**: OOM with no restart option, NaN loss with no checkpoint to roll back to, 3 retries exhausted
- **User intervention needed**: ambiguous failure, hyperparameter decision needed, infrastructure issue outside Claude's reach
- **`--once` flag was passed**: after the first snapshot

When stopping, always output a final summary: total steps completed (or pipeline tasks), final metrics or error message, reason for stopping, and any recommended next steps.

Final summary format:

```text
Training Complete
=================
Target: <log/job>
Terminal state: SUCCEEDED | FAILED | CANCELLED | TIMEOUT
Steps completed: <N>/<total>
Final metrics: <metric>=<value>, ...
Best checkpoint: <path or none>

Decision: GO | NO-GO
Confidence: high|medium|low
```

`GO`: training reached a terminal `SUCCEEDED` state with no unresolved critical anomalies.
`NO-GO`: terminal state is `FAILED`, `CANCELLED`, or `TIMEOUT` with unresolved blockers.

### JSON artifact

Write `babysit-training.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` when training succeeded; `NO-GO` when terminal state is a failure
- `terminal_state`, `total_steps`, `final_metrics`, `best_checkpoint`
- `anomalies_detected`: one entry per anomaly observed during monitoring
- `findings`: surface each critical/high anomaly as a finding

## Example sessions

**Local/remote training (with exponential backoff):**

```
/ml-skills:babysit-training user@gpu-box:~/runs/gpt2-finetune/train.log --interval 30

[10:03:00] Connecting to gpu-box...
[10:03:01] Process found: PID 48291 (torchrun, 4 GPUs)
[10:03:01] Step 340/5000 (6.8%) | loss=2.41 | lr=3e-4 | grad_norm=1.2 | 98 samples/s
           GPU: 97% util, 62/80 GB VRAM | ETA: ~13h 20m | next poll in 30s

[10:03:31] Step 342/5000 (6.8%) | loss=2.39 | lr=3e-4 | grad_norm=1.1 | 99 samples/s
           GPU: 97% util | ETA: ~13h 18m | next poll in 45s  ← backed off 30s→45s

[10:04:16] Step 345/5000 (6.9%) | loss=2.38 | lr=3e-4 | grad_norm=1.1 | 99 samples/s
           GPU: 97% util | ETA: ~13h 15m | next poll in 68s  ← backed off 45s→68s

[10:05:24] Step 349/5000 (7.0%) | loss=nan — ANOMALY: NaN loss detected
  grad_norm spiked to 1842 at step 348. Last checkpoint: step 340 (2m ago).
  Interval reset to 30s.
  Recommended: roll back to step 340 and reduce lr. Awaiting your approval.
```

**Vertex AI Pipeline:**

```
/ml-skills:babysit-training --vertex-pipeline my-llm-pipeline --project my-gcp-proj --interval 120

[10:00:00] Pipeline: my-llm-pipeline
  Job: projects/my-gcp-proj/locations/us-central1/pipelineJobs/1234567890
  State: RUNNING | Started: 10 minutes ago
  Tasks: 1 SUCCEEDED (data-validation), 1 RUNNING (model-training), 3 PENDING

[10:02:00] Tasks: 1 SUCCEEDED, 1 RUNNING (model-training — 12 min elapsed), 3 PENDING — OK

[10:04:00] Tasks: 1 SUCCEEDED, 1 FAILED (model-training), 3 PENDING — ANOMALY: Task failed
  Fetching task logs from Cloud Logging...
  Error: CUDA out of memory on worker 0. Allocated 23.8 GB, needed 24.5 GB.
  Recommendation: reduce batch size or enable gradient checkpointing. Awaiting your approval.
```

**Vertex AI Custom training job:**

```
/ml-skills:babysit-training --vertex-training 9876543210 --project my-gcp-proj

[10:00:00] Custom job: projects/my-gcp-proj/locations/us-central1/customJobs/9876543210
  State: RUNNING | Machine: n1-standard-8 + 2x NVIDIA_TESLA_V100
  Recent log: Step 200/5000 | loss=2.31 | lr=3e-4

[10:00:30] State: SUCCEEDED | Duration: 4h 12m
  Final log: Training complete. Best checkpoint: gs://my-bucket/checkpoints/step-4800/
  Done. Monitoring complete.
```

## Additional resources

- [references/common-issues.md](references/common-issues.md) — Anomaly descriptions and fix strategies
- [references/log-formats.md](references/log-formats.md) — How to parse common training log formats
- [references/vertex-ai.md](references/vertex-ai.md) — Vertex AI Pipelines and Custom Jobs monitoring
- [scripts/tail-remote.sh](scripts/tail-remote.sh) — Helper for tailing remote logs over SSH
- [scripts/check-process.sh](scripts/check-process.sh) — Process health checker (local or remote)
