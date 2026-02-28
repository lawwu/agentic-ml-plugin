---
name: check-failed-run
description: Diagnoses failed or unstable machine learning training runs across local logs, artifact directories, process targets, experiment trackers, and Vertex AI pipelines. Collects evidence, classifies failure mode, performs root-cause analysis, and delivers a prioritized recovery plan. Run this automatically whenever a training job exits with an error, produces suspicious metrics, or is handed off for post-mortem review.
argument-hint: "[log-file | artifact-dir | --traceback | --pid PID | --proc NAME | --wandb RUN | --mlflow RUN | --vertex-pipeline JOB] [--project PROJECT] [--region REGION] [--framework pytorch|lightning|deepspeed|fsdp|tensorflow|jax] [--task classification|regression|language-modeling] [--last N]"
---

# Check Failed Run

Diagnose failed or unstable training runs, identify root causes, and return an evidence-backed fix plan.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `path/to/train.log` for local logs
- `user@host:/path/to/train.log` for remote logs
- `path/to/artifact-dir/` for run outputs (logs/config/checkpoints)
- `--traceback` for pasted traceback diagnosis
- `--pid PID` for process health + nearby logs
- `--proc NAME` for process-name lookup
- `--wandb RUN_ID` or `--mlflow RUN_ID` for experiment-tracker context
- `--vertex-pipeline JOB_ID_OR_NAME` for Vertex AI pipeline runs

Optional flags:

- `--project PROJECT` for GCP project (required for Vertex AI targets if no gcloud default exists)
- `--region REGION` for Vertex AI region (default: `us-central1`)
- `--framework` to narrow checks (`pytorch`, `lightning`, `deepspeed`, `fsdp`, `tensorflow`, `jax`)
- `--task` to tune expectations (`classification`, `regression`, `language-modeling`)
- `--target` for data/metric sanity checks tied to a label column
- `--last N` to limit tail parsing (default: 500 lines)
- `--artifacts PATH` to explicitly point to artifact directory
- `--interval N` for cloud polling interval seconds (default: 60 for Vertex AI)
- `--once` to run one-pass diagnosis and exit

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Collect evidence before proposing fixes

Gather concrete signals first:

- Run state: alive, crashed, hung, degraded, or completed with bad quality
- Last progress point: step/epoch/timestamp
- Exact failure signature plus 20-50 lines of surrounding context
- Metric trajectory: loss, grad_norm, lr, throughput, validation metric
- Environment clues: memory pressure, disk issues, process exit code

For `--vertex-pipeline`, collect:

- Pipeline resource name and top-level state (`RUNNING`, `FAILED`, `CANCELLED`, `SUCCEEDED`)
- Task breakdown: failed/running/pending task counts and failing task names
- `error` field from `gcloud ai pipeline-jobs describe`
- Recent Cloud Logging error events for the pipeline/task
- Last successful task and first failing task to isolate blast radius

For artifact directories, collect:

- Training config (`train_args.*`, `config.*`, `deepspeed_config.*`)
- Checkpoint inventory and timestamps
- Any failure artifacts (`stderr`, crash dumps, task metadata)

For remote logs, use [scripts/fetch-remote-log.sh](scripts/fetch-remote-log.sh) to fetch the log and companion config files in one step.

If evidence is missing, request the smallest additional artifact needed.

### 2. Classify the primary failure mode

Use one primary class and optional secondary contributors:

- `nan-inf`: loss/weights become NaN or Inf
- `oom`: CUDA/host memory exhaustion
- `optimization-divergence`: monotonic loss blow-up, unstable lr schedule
- `cuda-runtime`: CUDA runtime/device assertions
- `nccl-distributed`: NCCL/Gloo deadlocks, rank failures, timeouts
- `data-pipeline`: malformed batches, dtype/shape mismatch, corrupt samples
- `config-error`: invalid flags, model/config incompatibilities
- `io-checkpoint`: save/load errors, path permissions, storage quota
- `stalled`: no progress without explicit crash
- `process-crash`: SIGKILL/segfault/worker crash
- `evaluation-mismatch`: train improves while eval collapses due to split/leakage/config mismatch
- `pipeline-orchestration`: Vertex AI pipeline or component task failure
- `cloud-permissions-quota`: IAM/quota/resource provisioning failure before task logic runs

Always include why alternatives were ruled out. Full failure mode catalog with signals and severity is in [references/failure-taxonomy.md](references/failure-taxonomy.md).

### 3. Root-cause analysis

For the classified failure, provide:

1. Proximate cause: exactly where execution failed
2. Root cause: why it failed (config, data, environment, infrastructure)
3. Contributing factors: conditions that amplified the failure

Per-failure diagnosis procedures, log patterns, and framework-specific configs to check (HF Trainer, Lightning, DeepSpeed, FSDP) are in [references/root-cause-patterns.md](references/root-cause-patterns.md).

### 4. Produce a prioritized recovery plan

For each proposed action, include:

- Expected impact
- Risk level (`safe`, `needs-approval`, `dangerous`)
- Time-to-try estimate
- Validation criterion (what success looks like in the next 50-200 steps)

Prefer quick, reversible actions first. Order by impact x confidence / risk.

### 5. Fix policy

You may apply only low-risk operational fixes without approval:

- Re-running read-only diagnostics (log reads, `gcloud describe`, metrics pulls)
- Fetching remote logs/artifacts
- Re-pointing to an already existing valid checkpoint path
- Restarting only when restart command is explicit and unchanged

Require user approval before:

- Hyperparameter changes (lr, batch size, optimizer, precision mode)
- Data filtering/transforms that alter training distribution
- Re-submitting or mutating Vertex AI pipeline specs/parameters
- Canceling long-running cloud jobs
- Killing/restarting distributed workers by force
- Rolling back code or checkpoints

### 6. Report format

Use this compact structure:

```text
Status: <crashed|hung|degraded|diverged|recovered>
Framework: <detected|unknown>
Primary cause: <class> (confidence: <0.00-1.00>)
Contributing factors: <list or none>
Evidence:
- ...
- ...
Root cause:
<1-3 sentences>
Top fixes:
1) <action> | risk=<...> | expected impact=<...> | validate=<...>
2) <action> | risk=<...> | expected impact=<...> | validate=<...>
Decision: GO | NO-GO
Confidence: high|medium|low

Next command(s):
- <exact command>
```

`GO`: a clear recovery path exists; recommended fix is actionable and ready to attempt.
`NO-GO`: run is unrecoverable without user policy decisions (e.g., hyperparameter changes, checkpoint rollback).

For Vertex AI pipeline targets, include:

```text
Pipeline: projects/<project>/locations/<region>/pipelineJobs/<id>
Pipeline state: <RUNNING|FAILED|...>
Failed tasks: <name1,name2,...>
```

### 7. Stop conditions

Stop when one of these is true:

- A clear diagnosis and ranked plan has been delivered
- The run is stable again with confirmed forward progress
- User decision is required for medium/high-risk changes
- Available evidence is insufficient and the required artifact request is explicit

### JSON artifact

Write `check-failed-run.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` when a safe recovery path exists; `NO-GO` when user approval is required
- `run_status`, `primary_cause`, `primary_cause_confidence`, `contributing_factors`
- `evidence`, `root_cause`, `fixes`
- `findings`: one entry per top fix (severity `blocker` for critical issues, `high` for significant ones)

## Quick heuristics

- NaN within first 100 steps often indicates lr/precision/data-scaling issues
- NaN after many stable steps often indicates gradient explosion or corrupted late batches
- OOM after validation starts often points to eval batch size or accumulation mismatch
- NCCL timeout with no explicit error often means one rank crashed earlier
- `device-side assert triggered` often means label/index out of range
- Throughput collapse with stable loss often indicates data-loader or storage contention
- Perfect validation metrics unusually early often suggests leakage or split contamination
- `FAILED_PRECONDITION` in Vertex AI often points to missing data/artifact paths
- `PERMISSION_DENIED` usually indicates service-account IAM issues, not model code
- A pipeline with many `NOT_TRIGGERED` tasks usually has one upstream root failure to fix first

## Example

```text
/ml-skills:check-failed-run ./logs/train.log --framework pytorch --task language-modeling

Status: crashed
Framework: PyTorch
Primary cause: nan-inf (confidence: 0.86)
Contributing factors: fp16 enabled, no grad clipping
Evidence:
- step 1432: grad_norm jumped 12.4 -> 2781.9
- step 1433: loss=nan, AMP overflow warnings in previous 8 steps
- no CUDA OOM or data-loader exceptions observed
Root cause:
Gradient explosion under mixed precision caused unstable optimizer updates and NaN weights.
Top fixes:
1) Resume from last good checkpoint and reduce lr by 3x | risk=needs-approval | validate=no NaN for 300 steps
2) Enable grad clipping at 1.0 | risk=needs-approval | validate=grad_norm remains < 50
Next command(s):
- uv run python train.py --resume checkpoints/step_1400.pt --lr 1e-4 --max-grad-norm 1.0
```

```text
/ml-skills:check-failed-run --vertex-pipeline 1234567890 --project my-proj --region us-central1

Status: crashed
Framework: Vertex AI Pipeline component (trainer)
Primary cause: pipeline-orchestration (confidence: 0.82)
Contributing factors: regional GPU quota saturation
Pipeline: projects/my-proj/locations/us-central1/pipelineJobs/1234567890
Pipeline state: FAILED
Failed tasks: model-training
Evidence:
- pipeline error: RESOURCE_EXHAUSTED while provisioning 4xA100 workers
- task `model-training` failed after 6m; upstream data-validation succeeded
- Cloud Logging shows quota exceeded for NVIDIA_A100_GPUS
Top fixes:
1) Re-run pipeline in region with available quota or request quota increase | risk=needs-approval | validate=task enters RUNNING and stays healthy for 10m
2) Temporarily switch worker spec to available GPU type | risk=needs-approval | validate=pipeline passes provisioning and starts training
Next command(s):
- gcloud ai pipeline-jobs describe 1234567890 --project=my-proj --region=us-central1
- gcloud logging read "resource.labels.pipeline_job_id=1234567890 AND severity>=ERROR" --project=my-proj --limit=50
```
