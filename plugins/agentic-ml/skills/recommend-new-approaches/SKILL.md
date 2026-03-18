---
name: recommend-new-approaches
description: Recommend new research approaches, modeling ideas, and loss function modifications after a training run completes. Use this skill whenever you want to know what to try next, get modeling improvement suggestions, explore research ideas, suggest architecture changes, propose loss function modifications, or brainstorm next experiments based on the trained model and its metrics. Invoke automatically at the end of orchestrate-e2e or after check-eval to close the loop on every run with actionable next steps. Also use when the user asks "what should I try next?", "how can I improve this model?", "what experiments should I run?", or "what are some ideas to improve performance?".
argument-hint: "[--out-dir DIR] [--run-id ID] [--model PATH] [--eval-results PATH] [--train-results PATH] [--explain-results PATH] [--task-description TEXT] [--autoresearch]"
---

# Recommend New Approaches

Synthesize training artifacts into a prioritized list of research directions, modeling ideas, and loss function modifications — sorted by expected impact.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `--out-dir DIR` — directory containing run artifacts (default: `./reports/e2e-run`); the skill reads any JSON files found here
- `--run-id ID` — run ID shared across orchestrated run
- `--model PATH` — explicit path to trained model or checkpoint (overrides auto-discovery)
- `--eval-results PATH` — path to `check-eval.json` (default: `<out-dir>/check-eval.json`)
- `--train-results PATH` — path to `train-model.json` (default: `<out-dir>/train-model.json`)
- `--explain-results PATH` — path to `explain-model.json` (default: `<out-dir>/explain-model.json`)
- `--task-description TEXT` — plain-language description of the task and business context (augments artifact data)
- `--autoresearch` — if set, attempt to use [autoresearch](https://github.com/karpathy/autoresearch) for automated literature-grounded suggestions (requires `autoresearch` installed)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Load and synthesize run artifacts

Collect all available signals from `--out-dir` or explicit paths:

- `train-model.json` — final metrics, hyperparameters, early stopping info, training duration, best checkpoint
- `check-eval.json` — task scores, baseline deltas, regressions, best gains
- `explain-model.json` — top features, PDP shapes, bias audit findings, unexpected patterns
- `babysit-training.json` — anomalies detected during training (NaN/OOM/divergence/stalled)
- `check-dataset-quality.json` — dataset profile, class imbalance, data quality findings
- `review-target.json` — task type, leakage risks, split strategy
- `plan-experiment.json` — original hypothesis, model family, HP search space

If no artifacts are found, ask for at least one of `--eval-results` or `--train-results` before proceeding. Work with partial data when only some artifacts are present — note which signals were unavailable.

### 2. Diagnose the current model's weaknesses

Before generating ideas, build a brief diagnostic picture:

- **Performance gap**: how far is the model from the promotion threshold or an ideal score?
- **Training dynamics**: did training converge smoothly, plateau early, or show instability?
- **Evaluation patterns**: which tasks/slices/classes underperform? Any regressions vs. baseline?
- **Feature signal**: are top features plausible? Any unexpected patterns or bias findings?
- **Data constraints**: class imbalance, small dataset, noisy labels, distribution shift signals?

This diagnostic shapes the recommendations — don't skip it even if only one artifact is available.

### 3. Generate recommendations

Produce **5–15 specific, actionable recommendations** across these categories:

| Category | Examples |
|---|---|
| `architecture` | model family change, depth/width, attention mechanism, inductive biases |
| `loss` | focal loss for imbalance, label smoothing, contrastive objectives, auxiliary heads |
| `data` | augmentation strategy, oversampling/undersampling, semi-supervised data, synthetic data |
| `training` | learning rate schedule, warmup, gradient clipping, mixed precision, longer training |
| `regularization` | dropout rate, weight decay, early stopping patience, data augmentation as regularizer |
| `other` | ensembling, distillation, transfer from related task, feature interaction terms |

For each recommendation:

- Ground it in a specific signal from the artifacts (e.g., "eval_loss plateaued at step 2800 → suggest cosine annealing with restarts")
- Estimate **expected impact** (`high` / `medium` / `low`) based on the gap between current performance and where this idea could take it
- Estimate **effort** (`high` / `medium` / `low`) based on implementation complexity and compute cost
- Provide a concrete `next_command` when possible (e.g., a CLI flag change, a one-liner code edit, or a training command)

Sort all recommendations by `expected_impact` descending, breaking ties by `effort` ascending (high impact + low effort first).

### 4. Optionally run autoresearch

If `--autoresearch` is set, read the [autoresearch](https://github.com/karpathy/autoresearch) repo and attempt to use it to run some of the recommendations you generated if they fit the autoresearch use case (iterations that take less than 5 mins but can run many of them)

```bash
uv run autoresearch "<task description derived from artifacts>" --max-papers 10 --output <out-dir>/autoresearch-results.json
```

Parse the results and merge any literature-grounded suggestions into the recommendation list, tagging them with `"source": "autoresearch"`. If `autoresearch` is unavailable or fails, log a warning and continue with artifact-only recommendations.

Even without `--autoresearch`, you may draw on your knowledge of relevant ML literature to support recommendations — cite paper names or techniques by name where helpful.

### 5. Output a prioritized report

After generating recommendations, produce a readable summary:

```text
Recommended Next Approaches
===========================
Model: <checkpoint or model ID>
Task: <task_type> — <primary_metric>=<score> (baseline delta: <delta>)
Diagnostic: <2-3 sentence summary of key weaknesses>

Top Recommendations (sorted by expected impact):

#1 [HIGH impact / LOW effort] — <category>: <idea title>
   Rationale: <why this matters given the artifacts>
   Next step: <concrete command or code change>

#2 [HIGH impact / MEDIUM effort] — <category>: <idea title>
   ...

Decision: CONDITIONAL
Confidence: medium
```

Use `CONDITIONAL` as the decision (these are forward-looking suggestions, not a hard gate). Use `GO` if the model already looks strong and only minor improvements remain.

### JSON artifact

Write `recommend-new-approaches.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `CONDITIONAL` in most cases (recommendations exist); `GO` if model is already near-optimal
- `model`, `task_type`, `primary_metric`, `current_score`, `baseline_score`, `performance_gap`
- `diagnostic_summary`: 2–3 sentence summary of key weaknesses
- `recommendations`: array sorted by `expected_impact` descending — see schema for full shape
- `autoresearch_used`: `true` / `false`
- `autoresearch_path`: path to autoresearch output file, or `null`
- `artifacts_used`: list of artifact paths that were loaded

## Example session

```
/ml-skills:recommend-new-approaches --out-dir ./reports/run-001

Loading artifacts from ./reports/run-001:
  ✓ train-model.json — eval_loss=0.312, eval_f1=0.891 (early stopped at step 3200, patience=3)
  ✓ check-eval.json  — f1=0.891 vs. baseline 0.712 (+0.179); no regressions
  ✓ explain-model.json — top feature: transaction_amount_zscore; bias: disparate_impact=0.72 (failed)
  ✗ plan-experiment.json — not found, skipping

Diagnostic:
  Model trained well (F1 +0.179 over baseline) but stopped early at 32% of planned steps,
  suggesting the LR schedule may be too aggressive. Bias audit failed on disparate_impact (0.72 < 0.80),
  and the top feature shows heavy reliance on a single zscore — possible brittleness to distribution shift.

Recommended Next Approaches
===========================
Model: ./checkpoints/checkpoint-2800
Task: classification — eval_f1=0.891 (baseline delta: +0.179)

#1 [HIGH impact / LOW effort] — training: Cosine annealing with warm restarts
   Rationale: Early stopping triggered at step 3200 (patience=3) — LR plateau likely cause.
              Cosine restarts let training escape local minima without manual tuning.
   Next step: uv run train.py --lr_scheduler cosine_with_restarts --warmup_steps 200

#2 [HIGH impact / MEDIUM effort] — loss: Add fairness regularization term
   Rationale: disparate_impact=0.72 failed the 0.80 threshold. Adversarial debiasing or
              a fairness penalty on the loss can close the gap without major accuracy loss.
   Next step: Add FairLearn or AIF360 constraint wrapper around the training objective.

#3 [MEDIUM impact / LOW effort] — regularization: Increase early stopping patience to 7
   Rationale: patience=3 may be too tight — model stopped before plateau confirmed.
              A patience of 5–10 is common for tasks with noisy eval metrics.
   Next step: --early-stop-patience 7

...

Decision: CONDITIONAL
Confidence: medium

Artifact: ./reports/run-001/recommend-new-approaches.json
```

## Additional resources

- [autoresearch](https://github.com/karpathy/autoresearch) — automated literature-grounded research ideation
- [check-eval](../check-eval/SKILL.md) — evaluation results (primary input)
- [explain-model](../explain-model/SKILL.md) — feature importance and bias (supporting input)
- [train-model](../train-model/SKILL.md) — training artifacts (supporting input)
- [../../references/schemas.md](../../references/schemas.md) — JSON artifact schema
- [../../references/vocabulary.md](../../references/vocabulary.md) — canonical enum values
