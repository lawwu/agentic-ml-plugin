# Vertex AI Monitoring Reference

Reference for the `babysit-training` skill. Use this when monitoring Vertex AI Pipelines or Custom training jobs.

---

## Prerequisites

Ensure `gcloud` CLI is authenticated and a default project is set:

```bash
gcloud auth list                      # check active account
gcloud config get-value project       # get default project
gcloud config set project PROJECT_ID  # set if needed
```

The `aiplatform.googleapis.com` service must be enabled:
```bash
gcloud services enable aiplatform.googleapis.com
```

---

## Vertex AI Pipeline Jobs

### Get pipeline job status

```bash
# By job ID
gcloud ai pipeline-jobs describe JOB_ID \
  --region=us-central1 \
  --project=PROJECT_ID

# Output includes: state, createTime, startTime, endTime, error, pipelineSpec
```

Or using Python SDK:
```python
from google.cloud import aiplatform
aiplatform.init(project="PROJECT_ID", location="us-central1")
job = aiplatform.PipelineJob.get("projects/PROJECT_ID/locations/REGION/pipelineJobs/JOB_ID")
print(job.state)        # e.g. PipelineState.PIPELINE_STATE_RUNNING
print(job.task_details) # per-task status
```

### List recent pipeline jobs

```bash
gcloud ai pipeline-jobs list \
  --region=us-central1 \
  --project=PROJECT_ID \
  --limit=10 \
  --format="table(name,displayName,state,createTime)"
```

### Pipeline job states

| State | Meaning |
|---|---|
| `PIPELINE_STATE_QUEUED` | Accepted, waiting to start |
| `PIPELINE_STATE_PENDING` | Preparing infrastructure |
| `PIPELINE_STATE_RUNNING` | Actively executing |
| `PIPELINE_STATE_SUCCEEDED` | Completed successfully — terminal |
| `PIPELINE_STATE_FAILED` | Completed with failure — terminal |
| `PIPELINE_STATE_CANCELLING` | Cancel requested, still running |
| `PIPELINE_STATE_CANCELLED` | Cancelled — terminal |
| `PIPELINE_STATE_PAUSED` | Paused |

Terminal states: `SUCCEEDED`, `FAILED`, `CANCELLED`.

### Task-level states

Each task within a pipeline has its own state:

| State | Meaning |
|---|---|
| `TASK_STATE_RUNNING` | Currently executing |
| `TASK_STATE_SUCCEEDED` | Completed successfully |
| `TASK_STATE_FAILED` | Completed with failure |
| `TASK_STATE_SKIPPED` | Skipped (condition not met) |
| `TASK_STATE_NOT_TRIGGERED` | Upstream dependency failed |
| `TASK_STATE_PENDING` | Waiting for upstream task |
| `TASK_STATE_CANCELLING` | Cancel in progress |
| `TASK_STATE_CANCELLED` | Cancelled |

Fetch task details via Python SDK:
```python
for task in job.task_details:
    print(task.task_name, task.state, task.start_time, task.end_time)
    if task.error:
        print("Error:", task.error.message)
```

### Read pipeline job logs (Cloud Logging)

```bash
# Job-level events
gcloud logging read \
  "resource.type=aiplatform.googleapis.com/PipelineJob AND resource.labels.pipeline_job_id=JOB_ID" \
  --project=PROJECT_ID \
  --limit=50 \
  --format="table(timestamp,severity,jsonPayload.message)"

# Task-level events (more granular)
gcloud logging read \
  "logName=projects/PROJECT_ID/logs/aiplatform.googleapis.com%2Fpipeline_job_task_events AND resource.labels.pipeline_job_id=JOB_ID" \
  --project=PROJECT_ID \
  --limit=100

# Filter to errors only
gcloud logging read \
  "resource.labels.pipeline_job_id=JOB_ID AND severity>=ERROR" \
  --project=PROJECT_ID \
  --limit=20
```

### Cancel a pipeline job

```bash
gcloud ai pipeline-jobs cancel JOB_ID \
  --region=us-central1 \
  --project=PROJECT_ID
```

---

## Vertex AI Custom Training Jobs

### Get custom job status

```bash
gcloud ai custom-jobs describe JOB_ID \
  --region=us-central1 \
  --project=PROJECT_ID
```

Output includes: `state`, `createTime`, `startTime`, `endTime`, `error`, `workerPoolSpecs`.

### List recent custom jobs

```bash
gcloud ai custom-jobs list \
  --region=us-central1 \
  --project=PROJECT_ID \
  --limit=10 \
  --format="table(name,displayName,state,createTime)"
```

### Custom job states

| State | Meaning |
|---|---|
| `JOB_STATE_QUEUED` | Accepted, waiting to start |
| `JOB_STATE_PENDING` | Preparing infrastructure |
| `JOB_STATE_RUNNING` | Actively executing |
| `JOB_STATE_SUCCEEDED` | Completed successfully — terminal |
| `JOB_STATE_FAILED` | Completed with failure — terminal |
| `JOB_STATE_CANCELLING` | Cancel requested |
| `JOB_STATE_CANCELLED` | Cancelled — terminal |
| `JOB_STATE_PAUSED` | Paused |
| `JOB_STATE_EXPIRED` | Timed out — terminal |

Terminal states: `SUCCEEDED`, `FAILED`, `CANCELLED`, `EXPIRED`.

### Read custom job logs (Cloud Logging)

Custom training jobs write container stdout/stderr to Cloud Logging:

```bash
# Stream logs for a running job
gcloud logging read \
  "resource.type=ml_job AND resource.labels.job_id=JOB_ID" \
  --project=PROJECT_ID \
  --freshness=10m \
  --limit=100 \
  --order=asc

# Filter to errors only
gcloud logging read \
  "resource.type=ml_job AND resource.labels.job_id=JOB_ID AND severity>=ERROR" \
  --project=PROJECT_ID \
  --limit=20
```

Or using Python SDK to stream logs during job:
```python
job = aiplatform.CustomJob.get("projects/PROJECT_ID/locations/REGION/customJobs/JOB_ID")
# job.wait() blocks; for polling, check job.state
```

### Cancel a custom job

```bash
gcloud ai custom-jobs cancel JOB_ID \
  --region=us-central1 \
  --project=PROJECT_ID
```

---

## Polling strategy for Vertex AI targets

Since Vertex AI jobs can run for hours, the default poll interval is 60 seconds (overridable with `--interval`).

**Recommended polling sequence:**
1. `gcloud ai pipeline-jobs describe` (or `custom-jobs describe`) to get current state
2. For pipelines: check task-level states in the response
3. If state is running, fetch last N log lines from Cloud Logging
4. Parse log lines for training metrics (loss, accuracy) and error messages
5. Check for anomaly signals
6. Sleep for interval, then repeat

**When a task or job enters FAILED state:**
1. Immediately fetch the `error` field from the describe output
2. Read the last 50 log lines from Cloud Logging for that job/task
3. Search for the root cause: OOM, Python exception, timeout, data error
4. Report findings and recommended fix to user before taking any action

---

## Common Vertex AI failure modes

| Error | Common Cause | Investigation |
|---|---|---|
| `RESOURCE_EXHAUSTED` | GPU/CPU quota exceeded | Check quota in Cloud Console |
| `DEADLINE_EXCEEDED` | Job hit max runtime | Increase `timeout` in job spec |
| `OUT_OF_MEMORY` | Container OOM | Check machine type, reduce batch size |
| `FAILED_PRECONDITION` | Input data missing | Check GCS paths in job spec |
| `PERMISSION_DENIED` | Service account missing permissions | Check IAM roles |
| `NOT_FOUND` | Container image or data not found | Verify image and GCS URIs |
| Worker crash (exit code != 0) | Python exception or CUDA error | Read container logs in Cloud Logging |

---

## Useful Python SDK snippets

```python
from google.cloud import aiplatform
aiplatform.init(project="my-project", location="us-central1")

# Get pipeline job
job = aiplatform.PipelineJob.get("projects/my-proj/locations/us-central1/pipelineJobs/JOB_ID")
print(job.state)

# List recent pipeline jobs
jobs = aiplatform.PipelineJob.list(
    filter='state="PIPELINE_STATE_RUNNING"',
    order_by="create_time desc",
)

# Get custom training job
custom_job = aiplatform.CustomJob.get("projects/my-proj/locations/us-central1/customJobs/JOB_ID")
print(custom_job.state)
print(custom_job.resource_name)
```
