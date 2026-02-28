---
name: benchmark-e2e
description: Benchmarks end-to-end ML execution quality across multiple modes (no-plugin/manual, plugin-driven, and AutoGluon-backed AutoML). Automatically identifies exactly one dataset scenario (hard-fraud or hard-attrition) and runs the benchmark against that single scenario. Use when asked to compare E2E workflows, measure agent reliability/cost/speed, or recommend which skills should be used for the detected scenario.
argument-hint: "[--modes no-plugin,plugin,automl|autogluon] [--scenario auto|hard-fraud|hard-attrition] [--dataset PATH] [--label-col COLUMN] [--metric METRIC] [--runs N] [--out-dir DIR]"
disable-model-invocation: true
---

# Benchmark E2E

Run a structured benchmark of end-to-end ML execution paths and produce a comparable scorecard.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `--modes` — benchmark targets; default: `no-plugin,plugin,automl` (where `automl` maps to AutoGluon; `autogluon` alias accepted)
- `--scenario` — `auto` (default), `hard-fraud`, or `hard-attrition`
- `--dataset` — dataset path/ID (required unless scenario specifies source)
- `--label-col` — target column
- `--metric` — primary metric for quality scoring
- `--runs N` — repeats per mode for the selected scenario (default: 1)
- `--out-dir DIR` — report/artifact directory (default: `./reports/e2e-benchmark`)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Identify exactly one scenario

Determine one scenario before benchmarking:

- If `--scenario hard-fraud` or `--scenario hard-attrition` is passed, use it.
- Otherwise (`--scenario auto` or omitted), classify automatically using [references/scenarios.md](references/scenarios.md).
- You must select exactly one scenario: `hard-fraud` or `hard-attrition`.
- Never run both scenarios in one invocation.

If classification is ambiguous, default to `hard-attrition` and explain why.

### 2. Define benchmark matrix (single scenario)

Build only:

- Modes: requested subset of `no-plugin`, `plugin`, `automl` (AutoGluon)
- Scenario: the one selected in step 1

Generate the dataset from `demo/scenarios/<scenario>/generate_data.py` when no `--dataset` path is provided. See [references/datasets.md](references/datasets.md) for generation commands and benchmark configuration.

Document any assumptions.

### 3. Apply mode-specific flow

Use [references/modes.md](references/modes.md) to run each mode consistently. All modes must attempt all 8 lifecycle stages in order. A NO-GO at any stage is recorded but does not halt the benchmark — continue to the next stage so every cell has full coverage.

For each stage, record:

- start/end timestamps
- decision: `GO | NO-GO | CONDITIONAL | SKIPPED`
- commands run
- failures/retries
- final model metrics
- artifact paths

### 4. Capture execution telemetry

For each mode run, capture and report:

- `loc_run`: lines of code executed by the agent/mode (sum of executed script/code lines; exclude blank/comment-only lines)
- `tokens_in`: prompt/input tokens consumed
- `tokens_out`: completion/output tokens generated
- `tokens_total`: `tokens_in + tokens_out`

If a metric is unavailable, set it to `unknown` and note the source gap in the run notes.

### 5. Enforce skill usage mapping

For each run, apply the required skill chain from [references/skill-matrix.md](references/skill-matrix.md) and record:

- expected skills
- actually used skills
- missing/extra skills

For `no-plugin` and `automl` (AutoGluon), expected skills must be empty. Any skill invocation in either mode is an audit violation and must be reported as `extra`.

### 6. Score each run

Score along four axes:

- quality (primary metric and regression checks)
- reliability (completion rate, failures, retries)
- efficiency (wall time, approximate cost/compute, and token footprint)
- operational readiness (reproducibility + artifact completeness)

Use a consistent 0-100 scale per axis, then compute a weighted total.

### 7. Produce benchmark report

Create:

- run-level logs
- matrix summary table
- mode ranking for the selected scenario
- recommendation: best default mode + fallback mode

Use [scripts/init-report.sh](scripts/init-report.sh) to initialize report files.

## Output format

```text
E2E Benchmark Report
====================
Matrix: <modes x 1 scenario>
Selected scenario: <hard-fraud|hard-attrition> (detection: <auto|user-forced>)
Runs per cell: <N>
Primary metric: <metric>

Results:
| Mode   | Scenario      | Quality | Reliability | Efficiency | Ops Readiness | LOC Run | Tokens In | Tokens Out | Tokens Total | Total |
|-----------|---------------|---------|-------------|------------|---------------|---------|-----------|------------|--------------|-------|
| ...       | ...           | ...     | ...         | ...        | ...           | ...     | ...       | ...        | ...          | ...   |

Stage coverage:
| Stage | no-plugin | plugin | automl |
|---|---|---|---|
| 1. Target readiness | GO/NO-GO/SKIPPED | GO/NO-GO/SKIPPED | GO/NO-GO/SKIPPED |
| 2. Experiment plan | ... | ... | ... |
| 3. Dataset quality | ... | ... | ... |
| 4. Data pipeline | ... | ... | ... |
| 5. Training stability | ... | ... | ... |
| 6. Evaluation quality | ... | ... | ... |
| 7. Interpretability/bias | ... | ... | ... |
| 8. Promotion decision | GO/NO-GO | GO/NO-GO | GO/NO-GO |

Skill usage audit:
- Expected vs actual skills per cell
- Missing critical skills (if any)

Recommendation:
- Default mode: <...> (why)
- Fallback mode: <...> (why)
```

## Stop conditions

Stop when:

- the selected scenario is identified and every requested mode cell for that one scenario has a scored result, or
- a blocking dependency is missing and explicitly reported with retry command.

### JSON artifact

Write `benchmark-report.json` to `--out-dir` (default: `./reports/e2e-benchmark`) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

`benchmark-e2e` is a meta-skill; set `decision` to `GO` when benchmark completes normally. Populate `results` with one entry per mode and `recommendation` with the ranked conclusions.

## Additional resources

- [references/harnesses.md](references/harnesses.md) — agent harnesses and models (Claude Code, Codex, Gemini CLI)
- [references/modes.md](references/modes.md) — execution flow by mode (no-plugin, plugin, automl)
- [references/scenarios.md](references/scenarios.md) — scenario definitions and constraints
- [references/datasets.md](references/datasets.md) — benchmark dataset catalog and loading snippets
- [references/skill-matrix.md](references/skill-matrix.md) — required skills by mode/scenario
- [scripts/init-report.sh](scripts/init-report.sh) — benchmark report scaffold
