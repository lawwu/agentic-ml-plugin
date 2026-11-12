# Agentic ML Plugin

Agent skills for machine learning workflows for Claude Code and other agentic coding harnesses.

## Installation

### Claude Code

```bash
claude plugin marketplace add lawwu/agentic-ml-plugin
claude plugin install agentic-ml@agentic-ml
```

Restart Claude Code after installation. Skills activate automatically when relevant.

**Update:**

```bash
claude plugin marketplace update
claude plugin update agentic-ml@agentic-ml
```

Or run `/plugin` to open the plugin manager.

### Other agents (Cursor, Cline, GitHub Copilot, and others)

For agents supporting the [skills.sh](https://skills.sh) ecosystem:

```bash
npx skills add lawwu/agentic-ml-plugin
```

### Local Development

```bash
git clone git@github.com:lawwu/agentic-ml-plugin.git ~/agentic-ml-plugin
claude --plugin-dir ~/agentic-ml-plugin/plugins/agentic-ml
```

## Sample Prompts

The demo datasets are generated, not committed. From a clone of this repository, generate one first (it writes `demo/scenarios/medium/data.csv`):

```bash
uv run demo/scenarios/medium/generate_data.py
```

Run complete ML lifecycle:

```bash
/orchestrate-e2e on the medium dataset in demo/
```

Run complete ML lifecycle but use [mlscribe](https://github.com/lawwu/mlscribe) to output artifacts:

```bash
/orchestrate-e2e on the medium dataset in demo/ but use the mlscribe cli to show me some artifacts. see https://github.com/lawwu/mlscribe
```

Run it as a junior data scientist (explains each step and pauses at every gate):

```bash
/orchestrate-e2e on the medium dataset in demo/ --level junior
```

Decide what kind of ML/AI fits a problem before building anything:

```bash
/select-approach we want to cut the time support agents spend triaging tickets
```

## How it adapts to you

Tell the plugin your level once — `junior`, `senior`, or `staff` — with `--level`, or save it in `.claude/agentic-ml.local.md`:

```markdown
---
level: senior
autonomy: review-key-gates   # optional
---
We use conda, not uv. MLflow tracking server: http://mlflow.internal
```

| | junior | senior | staff |
|---|---|---|---|
| Explanations | Why each finding matters, with the pitfall named | Finding, evidence, fix | Blockers and high risks only |
| Pauses for review | Every gate | Target and split, before training, promotion | Only on NO-GO, approvals, and promotion |
| Code | Writes commented scaffolds into your project | Works with your code | Audits your code, notebooks, or PRs |

Level changes how the agent communicates and how often it stops for you. **It never changes the checks, thresholds, the locked test set, or what needs your approval.** See [levels.md](plugins/agentic-ml/references/levels.md).

## What makes the numbers trustworthy

- **An evidence notebook you can re-run.** Every skill records the command behind each headline number and each serious finding, with its real output, in one [showboat](https://github.com/simonw/showboat) notebook per run (`evidence.md`). `uvx showboat --workdir <out-dir> verify <out-dir>/evidence.md` re-runs it and shows any number that no longer reproduces; the orchestrator does this before promotion. See [evidence-notebook.md](plugins/agentic-ml/references/evidence-notebook.md).
- **The right kind of ML first.** `select-approach` checks whether you need ML at all, then picks between supervised learning, forecasting (including zero-shot time-series foundation models), unsupervised learning, embeddings, prompting an LLM, fine-tuning, RLHF/RLVR, or agents — cheapest first.
- **A locked test set.** The split is made once and the test set is read once, at promotion, with a hash check.
- **Uncertainty on every metric.** Bootstrap confidence intervals, a paired comparison against the baseline, slices, calibration, and an explicit operating point.
- **Provenance.** Git SHA, package versions, lockfile hashes, data hashes, and seeds in every artifact that touches data or code.
- **Pre-flight checks** before spending compute: loss at init, overfit one batch, save/resume, and too-good-to-be-true scores.
- **Deployment readiness.** Training/serving parity in a fresh process, latency budgets, a data contract and drift baseline, and monitoring and rollback plans.
- **ML Test Score.** Each run is scored against Google's 28-test production-readiness rubric, so "ready" means something specific.

The full rules are in [evaluation-protocol.md](plugins/agentic-ml/references/evaluation-protocol.md).

## Available Skills

| Stage | Skill | Lifecycle stage | Description |
|-------|-------|----------------|-------------|
| 0 | [select-approach](plugins/agentic-ml/skills/select-approach/SKILL.md) | Problem framing | Decide what kind of ML/AI fits — no ML, supervised, forecasting, unsupervised, embeddings, LLM prompting/RAG, fine-tuning, RLHF/RLVR, or agents — and which lifecycle skills apply |
| 1 | [review-target](plugins/agentic-ml/skills/review-target/SKILL.md) | Problem framing | Validate label/target definition, leakage risk, metric alignment, and split strategy; create the split and lock the test set |
| 2 | [check-dataset-quality](plugins/agentic-ml/skills/check-dataset-quality/SKILL.md) | Pre-training | Profile and validate CSV, Parquet, JSONL, HuggingFace datasets, database tables, or image directories; save a data contract and drift baseline |
| 3 | [build-baseline](plugins/agentic-ml/skills/build-baseline/SKILL.md) | Pre-training | Build non-ML baselines (plus statistical and time-series foundation-model baselines for forecasting) to establish the performance floor ML must beat |
| 4 | [plan-experiment](plugins/agentic-ml/skills/plan-experiment/SKILL.md) | Pre-training | Design a structured experiment plan with hypothesis, model candidates, HP search space, compute budget, and ordered execution |
| 4b | [feature-engineer](plugins/agentic-ml/skills/feature-engineer/SKILL.md) | Pre-training | Explore files or database tables and design leakage-safe feature sets tied to label and business outcome (optional; for raw data) |
| 5 | [check-data-pipeline](plugins/agentic-ml/skills/check-data-pipeline/SKILL.md) | Pre-training | Dry-run a preprocessing pipeline to catch shape, dtype, padding, and label issues — and tabular leakage (preprocessing, target encoding, resampling) |
| 6 | [train-model](plugins/agentic-ml/skills/train-model/SKILL.md) | Training | Pre-flight checks, native early stopping, sweeps, provenance, and tracking; includes a leakage-safe tabular training scaffold; delegates monitoring to babysit-training |
| 6b | [babysit-training](plugins/agentic-ml/skills/babysit-training/SKILL.md) | Training | Continuously monitor a training run (local, remote SSH, or Vertex AI) until it completes or hits a critical issue; can also be invoked standalone when training is already running |
| 6c | [check-failed-run](plugins/agentic-ml/skills/check-failed-run/SKILL.md) | Training | Diagnose a failed or unstable training run, classify root causes, and produce a prioritized recovery plan |
| 7 | [check-eval](plugins/agentic-ml/skills/check-eval/SKILL.md) | Post-training | Evaluate tabular models, predictions, HF checkpoints, or harness tasks with confidence intervals, paired baseline comparison, slices, and calibration; runs the one-time final test evaluation |
| 8 | [explain-model](plugins/agentic-ml/skills/explain-model/SKILL.md) | Post-eval | Generate feature importance, bias audit, and model card before promotion |
| 9 | [check-deployment-readiness](plugins/agentic-ml/skills/check-deployment-readiness/SKILL.md) | Pre-deployment | Training/serving parity, latency and memory budgets, data contract checks, and monitoring, rollout, and rollback plans |
| — | [demonstrate-value](plugins/agentic-ml/skills/demonstrate-value/SKILL.md) | Post-eval (informational) | Create a business value presentation whose figures are recorded and re-runnable with showboat |
| — | [build-review-page](plugins/agentic-ml/skills/build-review-page/SKILL.md) | Review (any gate) | Build one-minute HTML pages for the person approving a gate: one question per page, every number bound to a skill artifact and checked by a script, with the judgments only a human can make |
| — | [recommend-new-approaches](plugins/agentic-ml/skills/recommend-new-approaches/SKILL.md) | Post-eval (informational) | Recommend new research approaches, modeling ideas, and loss function modifications sorted by expected impact; optionally prepares an autoresearch experiment loop |
| — | [orchestrate-e2e](plugins/agentic-ml/skills/orchestrate-e2e/SKILL.md) | Orchestration | Coordinate the full ML lifecycle (gates 0–10) with review pauses by level, a final test evaluation, and an ML Test Score |
| — | [benchmark-e2e](plugins/agentic-ml/skills/benchmark-e2e/SKILL.md) | Meta | Compare E2E workflow approaches (no-plugin/plugin/automl) across scenarios (hard-fraud, hard-readmission, xhard-churn) to measure agent reliability, pitfall detection, and cost |

## Structured Output

Every skill writes a machine-readable JSON artifact alongside its text report. Artifacts share a [common base schema](plugins/agentic-ml/references/schemas.md) with consistent fields (`schema_version`, `skill_name`, `run_id`, `level`, `decision`, `confidence`, `findings`, `next_commands`, `provenance`) plus skill-specific extensions.

Canonical vocabulary (decision values, severities, gate statuses, approaches, levels) is defined in [vocabulary.md](plugins/agentic-ml/references/vocabulary.md). All skills use `GO / NO-GO / CONDITIONAL` for decisions and `blocker / high / medium / low` for severity.

When run via `orchestrate-e2e`, all skill artifacts are collected in `--out-dir` and an interactive HTML report is generated automatically:

```bash
uv run plugins/agentic-ml/skills/orchestrate-e2e/scripts/generate_report.py <out-dir>
# → <out-dir>/report.html
```

At each review pause, `build-review-page` writes short pages to `<out-dir>/review/` for the person approving the gate. Each answers one question (what am I approving, what is predicted and when, is the split leak-free, does it beat the baseline, where is it wrong, what does the cutoff cost, what else was tried). `check_page.py` fails a page whose numbers differ from the artifacts or whose artifacts changed after it was built.

The report includes a gate timeline, the level and approach, the evidence notebook with its verify status, an ML Test Score panel, metrics with confidence intervals, provenance, per-skill cards with findings tables, and raw JSON tabs.

## Sample Report from `/benchmark-e2e`

Recorded with the earlier stage order (experiment plan and baseline before the dataset-quality check).

```
  E2E Benchmark Report
  ====================
  Matrix: no-plugin × plugin × automl — 1 scenario
  Selected scenario: hard-fraud (detection: auto — is_fraud column + transaction_timestamp)
  Runs per cell: 1
  Primary metric: auprc
  Harness: Claude Code (claude-sonnet-4-6)

  Results:
  | Mode      | Scenario   | Quality | Reliability | Efficiency | Ops Readiness | LOC Run | Tokens In | Tokens Out | Tokens Total | Total |
  |-----------|------------|---------|-------------|------------|---------------|---------|-----------|------------|--------------|-------|
  | plugin    | hard-fraud |      60 |          80 |         45 |            85 |     380 |   unknown |    unknown |      unknown |    67 |
  | no-plugin | hard-fraud |      15 |          75 |         65 |            15 |     120 |   unknown |    unknown |      unknown |    40 |
  | automl    | hard-fraud |      12 |          55 |         75 |            10 |      45 |   unknown |    unknown |      unknown |    35 |

  Stage coverage:
  | Stage                  | no-plugin  | plugin       | automl       |
  |------------------------|------------|--------------|--------------|
  | 1. Target readiness    | NO-GO      | NO-GO        | NO-GO        |
  | 2. Experiment plan     | GO         | GO           | GO           |
  | 3. Non-ML baseline     | GO         | GO           | GO           |
  | 4. Dataset quality     | CONDITIONAL| NO-GO        | CONDITIONAL  |
  | 5. Data pipeline       | CONDITIONAL| CONDITIONAL  | CONDITIONAL  |
  | 6. Training stability  | GO         | GO           | GO           |
  | 7. Evaluation quality  | NO-GO      | CONDITIONAL  | NO-GO        |
  | 8. Interpretability    | NO-GO      | NO-GO        | NO-GO        |
  | 9. Promotion decision  | GO         | NO-GO        | GO           |

  Pitfall detection (hard-fraud):
  | Pitfall                           | no-plugin | plugin | automl |
  |-----------------------------------|:---------:|:------:|:------:|
  | Target echo (chargeback)          |     ✗     |   ✓    |   ✗    |
  | Near-perfect leak (dfp_age)       |     ✗     |   ✓    |   ✗    |
  | Wrong metric (AUC vs AUPRC)       |     ✗     |   ✓    |   ✗    |
  | Selection bias (5.96% reviewed)   |     ✗     |   ✓    |   ✗    |
  | Geographic proxy bias (ip_country)|     ✗     |   ✓    |   ✗    |
  | Split boundary tie                |     ✗     |   ✓    |   ✗    |

  Skill usage audit:
  - no-plugin: 0 skills (PASS — expected 0)
  - plugin: review-target, plan-experiment, build-baseline, check-dataset-quality, check-data-pipeline,
            check-eval, explain-model (babysit-training invoked inline — skill unavailable via tool)
  - automl: 0 skills (PASS — expected 0)

  Recommendation:
  - Default mode: plugin (why: only mode that catches leakage, enforces AUPRC, audits bias,
                  produces artifacts, and blocks promotion correctly; 67/100)
  - Fallback mode: no-plugin (why: more reliable than automl — no framework crashes,
                   better stage coverage; requires attentive analyst for leakage/metric)

  Notable finding: AutoGluon GBM crashed (exit 139) on ARM64 macOS + miniconda3 Python 3.11.5.
  RF and ExtraTrees ran. Fix: use uv-managed Python instead of miniconda3.

  Artifacts: reports/e2e-benchmark/20260227_164917/
    ├── README.md
    ├── benchmark-report.json
    ├── plugin/stage1/review-target.json
    ├── plugin/stage2/plan-experiment.json
    ├── plugin/stage3/build-baseline.json
    ├── plugin/stage4/check-dataset-quality.json
    ├── plugin/stage5/check-data-pipeline.json
    ├── plugin/stage6/babysit-training.json
    ├── plugin/stage7/check-eval.json
    ├── plugin/stage8/explain-model.json + MODEL_CARD.md + feature_importance.json
    ├── plugin/stage9-promotion.md
    └── automl/automl-stage-summary.json + ag_model/
```

## Contributing

### Creating New Skills

See [AGENTS.md](AGENTS.md) for full instructions, frontmatter reference, naming conventions, and skill design guidelines.

Quick path: create `plugins/agentic-ml/skills/<skill-name>/SKILL.md`, add frontmatter, write instructions, then update the table above.

### Test the Plugin Locally

```bash
claude --plugin-dir ./plugins/agentic-ml
```

### GitHub Actions

The workflows are locked: every action is pinned to an exact commit in `.github/workflows/actions.lock`, and the `actions` workflow checks the lockfile and lints the workflows with [zizmor](https://docs.zizmor.sh) on every pull request. After changing a workflow:

```bash
gh actions-lock          # relock (needs the gh-actions-lock extension: gh extension install github/gh-actions-lock)
uvx zizmor .github/      # lint
```

Keep comments off `uses:` lines: relocking rewrites those lines and drops anything at their end. Dependabot proposes action updates weekly, after a 7-day cooldown. Minor and patch updates merge themselves once the required "Actions lock" and "zizmor" checks pass; major updates wait for review.

## References

- [Agent Skills Specification](https://agentskills.io/specification)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
- [Claude Code Plugins Documentation](https://code.claude.com/docs/en/plugins)
