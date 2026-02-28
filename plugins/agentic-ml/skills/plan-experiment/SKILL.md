---
name: plan-experiment
description: Designs a structured ML experiment plan with hypothesis, model candidates, hyperparameter search space, compute budget, and experiment ordering. Invoke automatically whenever a user has a defined target and wants to start training — even if they just say "let's train a model", "I want to try a few models", or "what should I run first?" Running compute without an experiment plan wastes GPU hours and delays signal.
argument-hint: "[--task classification|regression|ranking|forecasting] [--data PATH|DATASET] [--metric METRIC] [--budget GPU_HOURS] [--max-candidates N] [--horizon DURATION]"
allowed-tools: Read, Grep, Glob, Bash
---

# Plan Experiment

Design a structured experiment plan before burning compute. Produce a prioritized ordering of model candidates with hypothesis, HP search space, compute estimates, and success criteria.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `--task` — modeling task type (classification, regression, ranking, forecasting)
- `--data PATH|DATASET` — dataset path or identifier
- `--metric METRIC` — primary evaluation metric (e.g., `f1`, `rmse`, `ndcg@10`)
- `--budget GPU_HOURS` — total compute budget in GPU-hours (default: ask)
- `--max-candidates N` — maximum model families to evaluate (default: 5)
- `--horizon DURATION` — prediction window if applicable

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Translate objective into a falsifiable ML hypothesis

State the hypothesis in the form:

> "We believe [model family] will achieve [metric] ≥ [threshold] on [dataset] within [compute budget], because [rationale]."

If the objective or metric is missing, invoke `review-target` before proceeding.

### 2. Select 2–5 model candidates

Always include:

- **Candidate #1**: simplest possible baseline (logistic regression, linear regression, decision tree, or frequency prior)
- Additional candidates ranked by expected signal per compute dollar

Use [references/hp-search-strategies.md](references/hp-search-strategies.md) for model family guidance. Cap at `--max-candidates` (default 5).

### 3. Define HP search space per candidate

For each candidate, specify:

- hyperparameter names, ranges, and scales (log, linear, categorical)
- search strategy (grid, random, Bayesian, successive halving)
- number of trials and early-stopping rule

Use [references/hp-search-strategies.md](references/hp-search-strategies.md) for family-specific default ranges.

### 4. Estimate compute requirements

For each candidate:

- estimate GPU-hours using [references/compute-estimation-guide.md](references/compute-estimation-guide.md)
- convert to approximate cost (use $3/GPU-hour as default cloud estimate unless user specifies)
- flag if total budget is exceeded; suggest pruning strategy

### 5. Set success/failure criteria and time-box

Define:

- primary success criterion (metric threshold to beat baseline)
- failure trigger (stop condition per candidate: no improvement after N trials, loss diverges, etc.)
- wall-clock time-box per candidate

### 6. Recommend experiment ordering

Order candidates by:

1. cheapest/fastest first (quick signal)
2. successive halving: allocate more budget to survivors
3. skip candidates if earlier results already beat success criterion

## Output format

```text
Experiment Plan
===============
Objective: <business outcome>
Hypothesis: <falsifiable statement>
Task: <task type>
Primary metric: <metric>
Dataset: <path/ID>
Total budget: <GPU-hours> (~$<cost>)

Model Candidates (ordered):
| # | Model family      | Rationale                | Est. GPU-hrs | Est. cost |
|---|-------------------|--------------------------|--------------|-----------|
| 1 | <baseline>        | <why>                    | <h>          | $<cost>   |
| 2 | <candidate>       | <why>                    | <h>          | $<cost>   |

HP Search Space:
Candidate 1 — <model>:
  <param>: range=[<lo>, <hi>], scale=<log|linear>, search=<strategy>

Success criteria:
- Primary: <metric> ≥ <threshold> vs. baseline
- Failure trigger per candidate: <condition>
- Time-box per candidate: <duration>

Experiment ordering:
1. Run <candidate> — expected <duration>, budget <GPU-hrs>
2. If criterion met: STOP and proceed to feature-engineer / check-data-pipeline
   If not: run <next candidate>

Decision: GO | NO-GO (missing: <what>)
```

### JSON artifact

Write `plan-experiment.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate from the plan output:
- `decision`: `GO` when plan is complete and ready; `NO-GO` when blocking input is missing
- `hypothesis`, `candidates`, `success_criteria`, `experiment_order`
- `findings`: one entry per blocker or gap (severity `blocker` for missing metric/dataset, `medium` for warnings)
- `next_commands`: ordered experiment run commands

## Quick heuristics

- No baseline → add one before any deep learning candidate; reject plan otherwise
- Budget < 1 GPU-hour for all candidates → suggest CPU-only models or reduce search trials
- Dataset < 10 K rows → warn against deep learning; prefer tree ensembles or linear models
- No metric chosen → request metric or invoke `review-target`
- User says "try everything" → cap at 5 model families / 50 trials total; apply successive halving
- All candidates are neural networks → add gradient-boosted trees as Candidate #2 (strong baseline for tabular data)

## Stop conditions

Stop when:

- experiment plan with all sections is complete and ordering is defined, or
- blocking input (metric, dataset, task type) is missing and explicitly requested.

## Additional resources

- [references/hp-search-strategies.md](references/hp-search-strategies.md) — HP ranges by model family and search algorithm selection
- [references/compute-estimation-guide.md](references/compute-estimation-guide.md) — GPU throughput heuristics and cost formulas
