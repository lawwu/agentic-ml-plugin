# Agentic ML Skills

A collection of agent skills for machine learning workflows, designed for [Claude Code](https://claude.ai/claude-code).

This repository is structured as a Claude Code plugin (see `plugins/agentic-ml/`), but the skills follow the open [Agent Skills specification](https://agentskills.io) format.

## Keep updated

When modifying or adding skills, keep these files in sync:

- `plugins/agentic-ml/references/schemas.md` — JSON output schemas for all skills
- `plugins/agentic-ml/references/vocabulary.md` — canonical enum values
- plugin version using semver (`plugins/agentic-ml/.claude-plugin/plugin.json`)
- `README.md` — Available Skills table and Repository Structure tree
- `CHANGELOG.md` — add an entry under `[Unreleased]` describing what changed

### Changelog conventions

`CHANGELOG.md` is updated manually alongside code changes. The GitHub release workflow (`.github/workflows/release.yml`) generates release notes independently from `git log` and does **not** read `CHANGELOG.md` — the two are maintained in parallel.

When bumping the plugin version for a release, move the `[Unreleased]` entries under a new versioned heading (e.g. `## [0.3.0] — YYYY-MM-DD`) before merging. Use the same category headings the release workflow uses:

- `### 🛠 Skills & Features` — new skills, new arguments, behavior changes
- `### 🐛 Bug Fixes` — correctness fixes
- `### 📚 Documentation` — README, AGENTS.md, reference docs
- `### 🔧 Maintenance` — CI, dependencies, refactors with no user-visible change

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

- In SKILL.md commands, reference bundled scripts as `"${CLAUDE_SKILL_DIR}/scripts/<script>"` so they resolve when the plugin is installed (the working directory is the user's project, not this repo). Keep markdown links relative (`[scripts/x.py](scripts/x.py)`).
- Put scripts inside the skill that runs them; files outside `skills/` are not available to other agent harnesses that install skills individually. Other skills reference them as `"${CLAUDE_PLUGIN_ROOT}/skills/<skill>/scripts/<script>"`. The one exception is `plugins/agentic-ml/scripts/provenance.py`, which every skill uses (`"${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py"`); skills must say what to record by hand when it is unavailable.
- Every Python script must declare its dependencies in a PEP 723 header (`# /// script`) with `requires-python = ">=3.10"`, so `uv run` works in a fresh environment.
- Scripts must not create files in the user's project as a side effect (for example, use `uv run --no-project` for inline Python).

## Skill Design Guidelines

- Do not mock data unless the user explicitly asks for it
- Skills are invoked automatically based on description matching — write descriptions that include the phrases a user or agent would naturally use at each lifecycle stage
- Each skill should produce a structured, parseable output (e.g. a severity-rated report, a Go/No-Go decision, a results table) so downstream skills and the orchestrator can act on it
- Every skill must include a **JSON artifact** subsection instructing the agent to write `<skill-name>.json` — see [plugins/agentic-ml/references/schemas.md](plugins/agentic-ml/references/schemas.md) for the base schema and per-skill extensions
- Every skill includes an **Adapt to the user's level** section that follows [plugins/agentic-ml/references/levels.md](plugins/agentic-ml/references/levels.md). Level changes explanation depth, pauses, and build-vs-review — never checks, thresholds, or approval rules
- Skills that compute or compare metrics follow [plugins/agentic-ml/references/evaluation-protocol.md](plugins/agentic-ml/references/evaluation-protocol.md): use the locked split, never read test rows outside `check-eval --final`, and report confidence intervals
- Artifacts from skills that read data or run code include `provenance`
- Every skill includes a **Record evidence** step that follows [plugins/agentic-ml/references/evidence-notebook.md](plugins/agentic-ml/references/evidence-notebook.md): it appends a section to the run's `evidence.md` with an `exec` block behind each headline number and each `blocker`/`high` finding. Blocks must be deterministic, side-effect free, and fast
- Use canonical vocabulary from [plugins/agentic-ml/references/vocabulary.md](plugins/agentic-ml/references/vocabulary.md) — `GO / NO-GO / CONDITIONAL` for decisions, `blocker / high / medium / low` for severity
- Prefer push-down computation (SQL, remote CLI) over pulling data locally when working with large datasets or remote systems
- Never auto-apply high-risk changes (hyperparameter edits, checkpoint rollbacks, job cancellations) — surface them as `needs-approval` actions and wait

## References

- [Rules of Machine Learning](https://developers.google.com/machine-learning/guides/rules-of-ml)
- [Agent Skills Specification](https://agentskills.io/specification)
- [Claude Code Skills Documentation](https://code.claude.com/docs/en/skills)
- [Claude Code Plugins Documentation](https://code.claude.com/docs/en/plugins)
