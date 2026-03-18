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

Run complete ML lifecycle:

```bash
/orchestrate-e2e on the medium dataset in demo/
```

Run complete ML lifecycle but use [mlscribe](https://github.com/lawwu/mlscribe) to output artfacts:

```bash
/orchestrate-e2e on the medium dataset in demo/ but use the mlscribe cli to show me some artifacts. see https://github.com/lawwu/mlscribe
```

## Available Skills

| Stage | Skill | Lifecycle stage | Description |
|-------|-------|----------------|-------------|
| 1 | [review-target](plugins/agentic-ml/skills/review-target/SKILL.md) | Problem framing | Validate label/target definition, leakage risk, metric alignment, and split strategy before modeling |
| 2 | [plan-experiment](plugins/agentic-ml/skills/plan-experiment/SKILL.md) | Pre-training | Design a structured experiment plan with hypothesis, model candidates, HP search space, compute budget, and ordered execution |
| 3 | [build-baseline](plugins/agentic-ml/skills/build-baseline/SKILL.md) | Pre-training | Build and evaluate non-ML baselines (majority class, mean predictor, simple rules) to establish the performance floor ML must beat |
| 4 | [check-dataset-quality](plugins/agentic-ml/skills/check-dataset-quality/SKILL.md) | Pre-training | Profile and validate CSV, Parquet, JSONL, HuggingFace datasets, database tables, or image directories |
| 5 | [check-data-pipeline](plugins/agentic-ml/skills/check-data-pipeline/SKILL.md) | Pre-training | Dry-run a preprocessing pipeline on a small sample to catch shape, dtype, padding, and label encoding issues |
| — | [feature-engineer](plugins/agentic-ml/skills/feature-engineer/SKILL.md) | Pre-training | Explore files or database tables and design leakage-safe feature sets tied to label and business outcome |
| 6 | [train-model](plugins/agentic-ml/skills/train-model/SKILL.md) | Training | Launch and manage training with early stopping, HP config, and checkpoint management; delegates monitoring to babysit-training |
| 6b | [babysit-training](plugins/agentic-ml/skills/babysit-training/SKILL.md) | Training | Continuously monitor a training run (local, remote SSH, or Vertex AI) until it completes or hits a critical issue; can also be invoked standalone when training is already running |
| 6c | [check-failed-run](plugins/agentic-ml/skills/check-failed-run/SKILL.md) | Training | Diagnose a failed or unstable training run, classify root causes, and produce a prioritized recovery plan |
| 7 | [check-eval](plugins/agentic-ml/skills/check-eval/SKILL.md) | Post-training | Evaluate a checkpoint via HF Trainer, lm-evaluation-harness, or a custom script with baseline comparison |
| 8 | [explain-model](plugins/agentic-ml/skills/explain-model/SKILL.md) | Post-eval | Generate feature importance, bias audit, and model card before promotion |
| 9 | [demonstrate-value](plugins/agentic-ml/skills/demonstrate-value/SKILL.md) | Post-eval | Create a visual business value presentation using showboat |
| 10 | [recommend-new-approaches](plugins/agentic-ml/skills/recommend-new-approaches/SKILL.md) | Post-eval | Recommend new research approaches, modeling ideas, and loss function modifications sorted by expected impact; optionally leverages autoresearch |
| — | [orchestrate-e2e](plugins/agentic-ml/skills/orchestrate-e2e/SKILL.md) | Orchestration | Coordinate the full ML lifecycle with explicit stage gates and a final Go/No-Go decision |
| — | [benchmark-e2e](plugins/agentic-ml/skills/benchmark-e2e/SKILL.md) | Meta | Compare E2E workflow approaches (no-plugin/plugin/automl) across scenarios (hard-fraud, hard-attrition, xhard-churn) to measure agent reliability, pitfall detection, and cost |

## Structured Output

Every skill writes a machine-readable JSON artifact alongside its text report. Artifacts share a [common base schema](plugins/agentic-ml/references/schemas.md) with consistent fields (`schema_version`, `skill_name`, `run_id`, `decision`, `confidence`, `findings`, `next_commands`) plus skill-specific extensions.

Canonical vocabulary (decision values, severities, gate statuses) is defined in [vocabulary.md](plugins/agentic-ml/references/vocabulary.md). All skills use `GO / NO-GO / CONDITIONAL` for decisions and `blocker / high / medium / low` for severity.

When run via `orchestrate-e2e`, all skill artifacts are collected in `--out-dir` and an interactive HTML report is generated automatically:

```bash
uv run plugins/agentic-ml/report-viewer/generate_report.py <out-dir>
# → <out-dir>/report.html
```

The report includes a gate timeline, per-skill collapsible cards with findings tables, and raw JSON tabs.

## Sample Report from `/benchmark-e2e`

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

```
claude --plugin-dir ./plugins/agentic-ml
```

## References

- [Agent Skills Specification](https://agentskills.io/specification)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
- [Claude Code Plugins Documentation](https://code.claude.com/docs/en/plugins)
