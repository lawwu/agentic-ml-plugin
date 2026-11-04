# Canonical Vocabulary

Shared enums used in all skill JSON artifacts. Use these exact strings — do not invent variants.

## Decision

| Value | Meaning |
|---|---|
| `GO` | All required checks pass; proceed to the next lifecycle stage |
| `NO-GO` | One or more blockers prevent proceeding; action required before continuing |
| `CONDITIONAL` | Proceed with documented caveats; risks acknowledged and tracked |

## Severity

| Value | Meaning |
|---|---|
| `blocker` | Invalidates evaluation or training; must be fixed before proceeding |
| `high` | Strong risk of instability, bias, or silent failure |
| `medium` | Quality debt; worth fixing before production |
| `low` | Informational; monitor but not urgent |

## Gate Status

| Value | Meaning |
|---|---|
| `PASS` | Gate criteria met; evidence recorded |
| `FAIL` | Gate criteria not met; blockers present |
| `SKIPPED` | Gate intentionally bypassed; rationale required |
| `PENDING` | Gate not yet executed |

## Terminal State

Used in `train-model` and `babysit-training` artifacts.

| Value | Meaning |
|---|---|
| `SUCCEEDED` | Training completed normally and reached the target steps/epochs |
| `FAILED` | Training exited with a non-zero status or unrecoverable error |
| `CANCELLED` | Training was cancelled by the user or an external signal |
| `TIMEOUT` | Training hit a wall-clock budget limit before completing |
| `EARLY_STOPPED` | Training was halted by early stopping logic before reaching max steps/epochs |

## Confidence

| Value | Meaning |
|---|---|
| `high` | Strong evidence; low ambiguity |
| `medium` | Adequate evidence; some uncertainty |
| `low` | Sparse evidence; interpret with caution |

When a skill also reports a numeric confidence (e.g. `check-failed-run`'s `primary_cause_confidence`), the base `confidence` field must agree with it: `≥ 0.8` → `high`, `0.5–0.8` → `medium`, `< 0.5` → `low`.

## Approach

Used by `select-approach` and `run-summary.json`. See [approach-guide.md](../skills/select-approach/references/approach-guide.md).

| Value | Meaning |
|---|---|
| `no-ml` | Rules, heuristics, SQL, or a dashboard meet the bar |
| `supervised` | Classification, regression, or ranking from labeled data |
| `forecasting` | Future values of time series (statistical, foundation-model, or trained) |
| `unsupervised` | Clustering, anomaly detection, segmentation, dimensionality reduction |
| `embeddings` | Semantic search, retrieval, deduplication, similarity, linear probes |
| `llm-prompting` | Off-the-shelf LLM with prompting, optionally with retrieval (RAG) |
| `llm-fine-tuning` | Supervised fine-tuning of an LLM (full, LoRA/QLoRA) or distillation |
| `preference-rl-tuning` | RLHF, DPO, or RL with verifiable rewards (RLVR) |
| `agent` | LLM with tools taking multi-step actions |

## Level

See [levels.md](levels.md). Changes communication and autonomy, never thresholds.

| Value | Meaning |
|---|---|
| `junior` | Explain each step and finding; pause at every gate; build scaffolds |
| `senior` | Terse findings with evidence; pause at key gates; work with the user's code |
| `staff` | Decisions, risks, and owners; pause only when required; audit existing work |

## Autonomy

| Value | Meaning |
|---|---|
| `review-every-gate` | Pause for review after every gate |
| `review-key-gates` | Pause after target and split lock, before training spend, and at promotion |
| `autonomous` | Pause only on `NO-GO`, `needs-approval`, and promotion |

## Baseline Kind

| Value | Meaning |
|---|---|
| `non-ml` | Rule-1 floor: no trained or pre-trained model |
| `statistical` | Classical statistical model (e.g. ETS, ARIMA, Theta) |
| `foundation-model` | Pre-trained model used zero-shot (e.g. a time-series foundation model) |
