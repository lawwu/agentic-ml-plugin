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

## Confidence

| Value | Meaning |
|---|---|
| `high` | Strong evidence; low ambiguity |
| `medium` | Adequate evidence; some uncertainty |
| `low` | Sparse evidence; interpret with caution |

## Legacy Term Mapping

When updating existing text output, normalize these terms to the canonical vocabulary:

| Skill | Legacy term | Canonical |
|---|---|---|
| plan-experiment | `BLOCKED` | `NO-GO` |
| plan-experiment | `GO (plan ready)` | `GO` |
| explain-model | `PROMOTE` | `GO` |
| explain-model | `PROMOTE-WITH-CAVEATS` | `CONDITIONAL` |
| explain-model | `DO-NOT-PROMOTE` | `NO-GO` |
| check-dataset-quality | `Go/No-Go: GO` | `GO` |
| check-dataset-quality | `Go/No-Go: NO-GO` | `NO-GO` |
| feature-engineer | _(no explicit decision)_ | add `GO / NO-GO / CONDITIONAL` |
| check-data-pipeline | _(implied pass/fail)_ | add explicit `GO / NO-GO` |
| babysit-training | _(no formal decision)_ | add `GO / NO-GO` based on terminal status |
| check-failed-run | _(status only)_ | add `GO / NO-GO` (GO = recoverable path identified) |
| check-eval | _(no explicit gate)_ | add `GO / NO-GO / CONDITIONAL` |
