@AGENTS.md

# Agentic ML Plugin — Codebase Guide

## Overview

This repository provides **11 autonomous ML agent skills** for Claude Code and other agentic coding harnesses. Skills run automatically based on description-matching and produce structured JSON artifacts alongside text reports. The plugin follows the open [Agent Skills specification](https://agentskills.io).

- **Plugin name:** `agentic-ml` (version `0.1.0`)
- **Author:** Lawrence Wu
- **Plugin entry:** `plugins/agentic-ml/`
- **Skill format:** `plugins/agentic-ml/skills/<skill-name>/SKILL.md`

---

## Repository Structure

```
agentic-ml-plugin/
├── CLAUDE.md                                     # This file (imports AGENTS.md)
├── AGENTS.md                                     # Skill authoring guidelines
├── README.md                                     # Installation, skills table, contributing
├── .markdownlint.yaml                            # Markdown lint config
├── .pre-commit-config.yaml                       # Pre-commit hooks
├── .github/workflows/validate-frontmatter.yml    # CI: validates SKILL.md frontmatter
├── .claude-plugin/marketplace.json               # Marketplace metadata
├── demo/scenarios/                               # Benchmark test datasets
│   ├── easy/
│   ├── medium/
│   ├── hard-fraud/          # Intentional leakage pitfalls (primary benchmark)
│   ├── hard-readmission/
│   └── xhard-churn/
└── plugins/agentic-ml/
    ├── .claude-plugin/plugin.json                # Plugin metadata
    ├── references/
    │   ├── schemas.md                            # JSON output schemas for all skills
    │   └── vocabulary.md                         # Canonical enum values
    ├── report-viewer/
    │   └── generate_report.py                    # HTML report generator
    └── skills/
        ├── review-target/
        ├── plan-experiment/
        ├── check-dataset-quality/
        ├── check-data-pipeline/
        ├── feature-engineer/
        ├── babysit-training/
        ├── check-failed-run/
        ├── check-eval/
        ├── explain-model/
        ├── orchestrate-e2e/
        └── benchmark-e2e/
```

Each skill directory follows this layout:

```
plugins/agentic-ml/skills/<skill-name>/
├── SKILL.md          # Main skill file with YAML frontmatter + instructions
├── references/       # Deep-dive markdown references (linked from SKILL.md)
│   └── <topic>.md
└── scripts/          # Helper scripts invoked by the agent
    └── <script>
```

---

## The 11 Skills

| Skill | Stage | Purpose |
|-------|-------|---------|
| `review-target` | Problem framing | Validates label definition, leakage risk, metric alignment, split strategy |
| `plan-experiment` | Pre-training | Designs hypothesis, model candidates, HP search space, compute budget |
| `check-dataset-quality` | Pre-training | Profiles CSV/Parquet/JSONL/HF datasets, DB tables, image dirs |
| `check-data-pipeline` | Pre-training | Dry-runs preprocessing to catch shape/dtype/padding/encoding issues |
| `feature-engineer` | Pre-training | Engineers leakage-safe features from files or databases |
| `babysit-training` | Training | Monitors local/SSH/Vertex AI training; detects NaN, OOM, divergence |
| `check-failed-run` | Training | Post-mortem diagnosis of failed/unstable runs with recovery plan |
| `check-eval` | Post-training | Evaluates checkpoints via HF Trainer/lm-eval/custom script vs baseline |
| `explain-model` | Post-eval | Feature importance, bias audit, model card; gates promotion |
| `orchestrate-e2e` | Orchestration | Coordinates all 8 lifecycle stages with NO-GO halt policy |
| `benchmark-e2e` | Meta | Compares no-plugin / plugin / automl approaches across scenarios |

### Lifecycle order

```
review-target → plan-experiment → check-dataset-quality → check-data-pipeline
→ feature-engineer → babysit-training → check-failed-run → check-eval
→ explain-model → orchestrate-e2e
```

`benchmark-e2e` is a meta-skill that runs all three modes (no-plugin, plugin, automl) and scores them.

---

## Key Conventions

### Canonical vocabulary

All skills use values from `plugins/agentic-ml/references/vocabulary.md`:

- **Decision:** `GO` | `NO-GO` | `CONDITIONAL`
- **Severity:** `blocker` | `high` | `medium` | `low`
- **Gate status:** `PASS` | `FAIL` | `SKIPPED` | `PENDING`
- **Confidence:** `high` | `medium` | `low`

### JSON artifact schema

Every skill writes `<skill-name>.json` to `--out-dir` (or `./` if standalone). All artifacts share a base schema defined in `plugins/agentic-ml/references/schemas.md`:

```json
{
  "schema_version": "1.0",
  "skill_name": "<kebab-case>",
  "run_id": "<uuid or timestamp-slug>",
  "timestamp": "<ISO-8601 UTC>",
  "duration_seconds": 42.3,
  "decision": "GO | NO-GO | CONDITIONAL",
  "confidence": "high | medium | low",
  "summary": "<one-liner>",
  "findings": [
    {
      "id": "F001",
      "severity": "blocker | high | medium | low",
      "title": "...",
      "description": "...",
      "fix": "..."
    }
  ],
  "next_commands": ["<shell command>"]
}
```

Each skill extends this with skill-specific fields (see `schemas.md`).

### Naming conventions

- `check-<noun>` — lifecycle gate skills (gating steps that can produce NO-GO)
- `<verb>-<noun>` — action skills that produce primary artifacts
- Keep `SKILL.md` under 500 lines; move deep content to `references/`

### SKILL.md frontmatter

```yaml
---
name: <skill-name>
description: <phrase users/agents naturally say at this lifecycle stage>
allowed-tools:
  - Bash
  - Read
  - Write
  - ...
---
```

Descriptions must match natural phrasing so the skill activates correctly.

---

## Development Workflows

### Adding a new skill

1. Create `plugins/agentic-ml/skills/<skill-name>/SKILL.md`
2. Add YAML frontmatter (`name`, `description`, `allowed-tools`)
3. Write markdown instructions (≤500 lines)
4. Add a **JSON artifact** section referencing `schemas.md` and `vocabulary.md`
5. Add reference docs to `references/` and scripts to `scripts/` as needed
6. Update these files to stay in sync:
   - `plugins/agentic-ml/references/schemas.md` — add schema for the new skill
   - `plugins/agentic-ml/references/vocabulary.md` — add any new enum values
   - `plugins/agentic-ml/.claude-plugin/plugin.json` — bump semver version
   - `README.md` — add row to Available Skills table + add to Repository Structure tree

### Running skills locally

```bash
# Load the plugin during a Claude Code session
claude --plugin-dir ./plugins/agentic-ml

# Generate HTML report from collected artifacts
uv run plugins/agentic-ml/report-viewer/generate_report.py <out-dir>
```

### Running Python scripts

Always use `uv run` (never `python` or `python3`):

```bash
uv run plugins/agentic-ml/skills/check-dataset-quality/scripts/profile-dataset.py <args>
uv run plugins/agentic-ml/report-viewer/generate_report.py <out-dir>
```

### Testing / pre-commit

```bash
pre-commit run --all-files
```

Pre-commit hooks validate: trailing whitespace, EOF newlines, YAML/JSON syntax, markdown linting, large files (>500 KB), private keys.

### CI validation

GitHub Actions (`.github/workflows/validate-frontmatter.yml`) runs on PRs touching `**/skills/*/SKILL.md` and validates YAML frontmatter using Bun + TypeScript.

---

## Design Principles

1. **No mocked data** — only work with real data unless the user explicitly requests mocking
2. **Autonomous invocation** — skills activate via description matching; write phrases users actually say
3. **Structured output** — every skill produces both human-readable text and machine-readable JSON
4. **Canonical vocabulary** — use `GO/NO-GO/CONDITIONAL` and `blocker/high/medium/low` everywhere
5. **NO-GO halt policy** — `orchestrate-e2e` stops immediately on any NO-GO gate
6. **Leakage-first** — target review, data quality, and pipeline checks run before any training
7. **Push-down computation** — prefer SQL/remote CLI over pulling large datasets locally
8. **No auto-apply on high-risk changes** — surface hyperparameter edits, checkpoint rollbacks, job cancellations as `needs-approval` actions and wait for user confirmation
9. **Evidence-driven findings** — findings reference specific column names, row indices, log lines, or file paths
10. **Reproducibility** — `next_commands` in every JSON artifact let any agent regenerate results

---

## Supporting Scripts

| Script | Skill | Purpose |
|--------|-------|---------|
| `check-dataset-quality/scripts/profile-dataset.py` | check-dataset-quality | Pandas-based statistical profiling (CSV/Parquet/JSONL) |
| `babysit-training/scripts/tail-remote.sh` | babysit-training | SSH-based remote log tailing |
| `babysit-training/scripts/check-process.sh` | babysit-training | Process health checker (local or remote) |
| `check-failed-run/scripts/fetch-remote-log.sh` | check-failed-run | Fetch remote logs + config in one step |
| `check-eval/scripts/compare-results.sh` | check-eval | JSON result delta formatting |
| `explain-model/scripts/feature_importance.py` | explain-model | Standardizes SHAP, permutation, builtin importance |
| `benchmark-e2e/scripts/init-report.sh` | benchmark-e2e | Benchmark report scaffold |
| `benchmark-e2e/scripts/generate_benchmark_report.py` | benchmark-e2e | HTML benchmark report generation |
| `report-viewer/generate_report.py` | orchestrate-e2e | Full HTML report from all collected JSON artifacts |

---

## Demo Scenarios

Located in `demo/scenarios/`. Each contains `generate_data.py` to produce test datasets.

| Scenario | Difficulty | Key challenge |
|----------|-----------|---------------|
| `easy/` | Easy | Baseline clean classification |
| `medium/` | Medium | Moderate complexity |
| `hard-fraud/` | Hard | Intentional leakage pitfalls (target echo, near-perfect leak, wrong metric, selection bias, geographic proxy, split boundary) |
| `hard-readmission/` | Hard | Hospital readmission with clinical leakage |
| `xhard-churn/` | Extra hard | Multiple simultaneous leakage vectors |

`hard-fraud/` is the primary benchmark scenario used to validate skill pitfall detection.

---

## Files to Keep in Sync

When adding or modifying skills, always update all of these:

| File | What to update |
|------|---------------|
| `plugins/agentic-ml/references/schemas.md` | Add/modify JSON schema for skill |
| `plugins/agentic-ml/references/vocabulary.md` | Add any new canonical enum values |
| `plugins/agentic-ml/.claude-plugin/plugin.json` | Bump `version` (semver) |
| `README.md` | Add row to Available Skills table; update Repository Structure tree |
