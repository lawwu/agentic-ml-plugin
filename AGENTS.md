# Agentic ML Skills

A collection of agent skills for machine learning workflows, designed for [Claude Code](https://claude.ai/claude-code).

This repository is structured as a Claude Code plugin (see `plugins/agentic-ml/`), but the skills follow the open [Agent Skills specification](https://agentskills.io) format.

## Keep updated

When modifying or adding skills, keep these files in sync:

- `plugins/agentic-ml/references/schemas.md` — JSON output schemas for all skills
- `plugins/agentic-ml/references/vocabulary.md` — canonical enum values
- plugin version using semver
- `README.md` — Available Skills table and Repository Structure tree

## Structure

```
plugins/agentic-ml/skills/<skill-name>/SKILL.md
```

Each skill is a directory containing a `SKILL.md` file with YAML frontmatter (`name`, `description`, `allowed-tools`) and markdown instructions.

Skills are lifecycle checks meant to run autonomously. Name them with the `check-` prefix where applicable so agents recognize them as gating steps in the ML workflow.

## Creating a Skill

1. Create `plugins/agentic-ml/skills/<skill-name>/SKILL.md`
2. Add YAML frontmatter (see below)
3. Write clear instructions in markdown
4. Add a **JSON artifact** subsection that references [references/schemas.md](plugins/agentic-ml/references/schemas.md) and [references/vocabulary.md](plugins/agentic-ml/references/vocabulary.md) — instruct the agent to write `<skill-name>.json` to `--out-dir` (or `./` if standalone)
5. Add supporting material to `references/` and scripts to `scripts/` as needed
6. Update `README.md` to include the new skill in the Available Skills table and Repository Structure tree

### Naming Conventions

- Use `check-<noun>` for lifecycle gate skills (e.g. `check-dataset-quality`, `check-eval`)
- Use `<verb>-<noun>` for action skills that produce artifacts (e.g. `feature-engineer`, `review-target`)
- Keep `SKILL.md` under 500 lines; move detailed reference material to `references/`

### References and Scripts

Skills with substantial reference material follow this layout:

```
plugins/agentic-ml/skills/<skill-name>/
├── SKILL.md
├── references/
│   └── <topic>.md      # linked from SKILL.md with relative paths
└── scripts/
    └── <script>        # helper scripts invoked by the agent
```

Python scripts should be invoked with `uv run <script>` rather than `python` or `python3`.

## Skill Design Guidelines

- Do not mock data unless the user explicitly asks for it
- Skills are invoked automatically based on description matching — write descriptions that include the phrases a user or agent would naturally use at each lifecycle stage
- Each skill should produce a structured, parseable output (e.g. a severity-rated report, a Go/No-Go decision, a results table) so downstream skills and the orchestrator can act on it
- Every skill must include a **JSON artifact** subsection instructing the agent to write `<skill-name>.json` — see [plugins/agentic-ml/references/schemas.md](plugins/agentic-ml/references/schemas.md) for the base schema and per-skill extensions
- Use canonical vocabulary from [plugins/agentic-ml/references/vocabulary.md](plugins/agentic-ml/references/vocabulary.md) — `GO / NO-GO / CONDITIONAL` for decisions, `blocker / high / medium / low` for severity
- Prefer push-down computation (SQL, remote CLI) over pulling data locally when working with large datasets or remote systems
- Never auto-apply high-risk changes (hyperparameter edits, checkpoint rollbacks, job cancellations) — surface them as `needs-approval` actions and wait

## References

- [Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml)
- [Agent Skills Specification](https://agentskills.io/specification)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
- [Claude Code Plugins Documentation](https://code.claude.com/docs/en/plugins)
