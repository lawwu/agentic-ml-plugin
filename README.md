# Agentic ML Plugin

Agent skills for machine learning workflows for Claude Code and other agenic coding harnesses.

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

## Available Skills

| Skill | Lifecycle stage | Description |
|-------|----------------|-------------|
| [review-target](plugins/agentic-ml/skills/review-target/SKILL.md) | Problem framing | Validate label/target definition, leakage risk, metric alignment, and split strategy before modeling |
| [plan-experiment](plugins/agentic-ml/skills/plan-experiment/SKILL.md) | Pre-training | Design a structured experiment plan with hypothesis, model candidates, HP search space, compute budget, and ordered execution |
| [check-dataset-quality](plugins/agentic-ml/skills/check-dataset-quality/SKILL.md) | Pre-training | Profile and validate CSV, Parquet, JSONL, HuggingFace datasets, database tables, or image directories |
| [check-data-pipeline](plugins/agentic-ml/skills/check-data-pipeline/SKILL.md) | Pre-training | Dry-run a preprocessing pipeline on a small sample to catch shape, dtype, padding, and label encoding issues |
| [feature-engineer](plugins/agentic-ml/skills/feature-engineer/SKILL.md) | Pre-training | Explore files or database tables and design leakage-safe feature sets tied to label and business outcome |
| [babysit-training](plugins/agentic-ml/skills/babysit-training/SKILL.md) | Training | Continuously monitor a training run (local, remote SSH, or Vertex AI) until it completes or hits a critical issue |
| [check-failed-run](plugins/agentic-ml/skills/check-failed-run/SKILL.md) | Training | Diagnose a failed or unstable training run, classify root causes, and produce a prioritized recovery plan |
| [check-eval](plugins/agentic-ml/skills/check-eval/SKILL.md) | Post-training | Evaluate a checkpoint via HF Trainer, lm-evaluation-harness, or a custom script with baseline comparison |
| [explain-model](plugins/agentic-ml/skills/explain-model/SKILL.md) | Post-eval | Generate feature importance, bias audit, and model card before promotion |
| [orchestrate-e2e](plugins/agentic-ml/skills/orchestrate-e2e/SKILL.md) | Orchestration | Coordinate the full ML lifecycle with explicit stage gates and a final Go/No-Go decision |
| [benchmark-e2e](plugins/agentic-ml/skills/benchmark-e2e/SKILL.md) | Meta | Compare E2E workflow approaches (no-plugin/plugin/automl) across scenarios (clean vs messy data) to measure agent reliability, cost, and speed |

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
  | 3. Dataset quality     | CONDITIONAL| NO-GO        | CONDITIONAL  |
  | 4. Data pipeline       | CONDITIONAL| CONDITIONAL  | CONDITIONAL  |
  | 5. Training stability  | GO         | GO           | GO           |
  | 6. Evaluation quality  | NO-GO      | CONDITIONAL  | NO-GO        |
  | 7. Interpretability    | NO-GO      | NO-GO        | NO-GO        |
  | 8. Promotion decision  | GO         | NO-GO        | GO           |

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
  - plugin: review-target, plan-experiment, check-dataset-quality, check-data-pipeline,
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
    ├── plugin/stage3/check-dataset-quality.json
    ├── plugin/stage4/check-data-pipeline.json
    ├── plugin/stage5/babysit-training.json
    ├── plugin/stage6/check-eval.json
    ├── plugin/stage7/explain-model.json + MODEL_CARD.md + feature_importance.json
    ├── plugin/stage8-promotion.md
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
