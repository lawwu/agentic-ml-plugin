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
