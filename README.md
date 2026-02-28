# Machine Learning Skills

Agent skills for machine learning workflows, following the [Agent Skills](https://agentskills.io) open format.

## Installation

### Claude Code

```bash
claude plugin marketplace add lawwu/ml-skills
claude plugin install ml-skills@ml-skills
```

Restart Claude Code after installation. Skills activate automatically when relevant.

**Update:**

```bash
claude plugin marketplace update
claude plugin update ml-skills@ml-skills
```

Or run `/plugin` to open the plugin manager.

### Local Development

```bash
git clone git@github.com:lawwu/ml-skills.git ~/ml-skills
claude --plugin-dir ~/ml-skills/plugins/ml-skills
```

## Available Skills

| Skill | Lifecycle stage | Description |
|-------|----------------|-------------|
| [check-dataset-quality](skills/check-dataset-quality/SKILL.md) | Pre-training | Profile and validate CSV, Parquet, JSONL, HuggingFace datasets, database tables, or image directories |
| [check-data-pipeline](skills/check-data-pipeline/SKILL.md) | Pre-training | Dry-run a preprocessing pipeline on a small sample to catch shape, dtype, padding, and label encoding issues |
| [review-target](skills/review-target/SKILL.md) | Problem framing | Validate label/target definition, leakage risk, metric alignment, and split strategy before modeling |
| [plan-experiment](skills/plan-experiment/SKILL.md) | Pre-training | Design a structured experiment plan with hypothesis, model candidates, HP search space, compute budget, and ordered execution |
| [feature-engineer](skills/feature-engineer/SKILL.md) | Pre-training | Explore files or database tables and design leakage-safe feature sets tied to label and business outcome |
| [babysit-training](skills/babysit-training/SKILL.md) | Training | Continuously monitor a training run (local, remote SSH, or Vertex AI) until it completes or hits a critical issue |
| [check-failed-run](skills/check-failed-run/SKILL.md) | Training | Diagnose a failed or unstable training run, classify root causes, and produce a prioritized recovery plan |
| [check-eval](skills/check-eval/SKILL.md) | Post-training | Evaluate a checkpoint via HF Trainer, lm-evaluation-harness, or a custom script with baseline comparison |
| [explain-model](skills/explain-model/SKILL.md) | Post-eval | Generate feature importance, bias audit, and model card before promotion |
| [orchestrate-e2e](skills/orchestrate-e2e/SKILL.md) | Orchestration | Coordinate the full ML lifecycle with explicit stage gates and a final Go/No-Go decision |
| [benchmark-e2e](skills/benchmark-e2e/SKILL.md) | Meta | Compare E2E workflow approaches (no-plugin/plugin/automl) across scenarios (clean vs messy data) to measure agent reliability, cost, and speed |

## Structured Output

Every skill writes a machine-readable JSON artifact alongside its text report. Artifacts share a [common base schema](plugins/agentic-ml/references/schemas.md) with consistent fields (`schema_version`, `skill_name`, `run_id`, `decision`, `confidence`, `findings`, `next_commands`) plus skill-specific extensions.

Canonical vocabulary (decision values, severities, gate statuses) is defined in [vocabulary.md](plugins/agentic-ml/references/vocabulary.md). All skills use `GO / NO-GO / CONDITIONAL` for decisions and `blocker / high / medium / low` for severity.

When run via `orchestrate-e2e`, all skill artifacts are collected in `--out-dir` and an interactive HTML report is generated automatically:

```bash
uv run plugins/agentic-ml/report-viewer/generate_report.py <out-dir>
# → <out-dir>/report.html
```

The report includes a gate timeline, per-skill collapsible cards with findings tables, and raw JSON tabs.

## Contributing

### Creating New Skills

See [AGENTS.md](AGENTS.md) for full instructions, frontmatter reference, naming conventions, and skill design guidelines.

Quick path: create `plugins/ml-skills/skills/<skill-name>/SKILL.md`, add frontmatter, write instructions, then update the table above and the structure tree below.

### Where Skills Belong

| Scope | Location |
|-------|----------|
| **General ML** — useful across projects | This repository |
| **Project-specific** — only relevant to one codebase | `.claude/skills/` in that repository |

## References

- [Agent Skills Specification](https://agentskills.io/specification)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
- [Claude Code Plugins Documentation](https://code.claude.com/docs/en/plugins)
