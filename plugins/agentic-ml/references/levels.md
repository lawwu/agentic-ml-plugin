# User Levels

Every skill adapts to the data scientist's level: `junior`, `senior`, or `staff`.

**The quality bar never changes with level.** Gates, thresholds, the locked test set, the evaluation protocol, and `needs-approval` rules are identical for everyone. Level changes three things only:

- how much the agent explains
- how often it pauses for review
- how much it builds versus reviews

## Resolving the level

Use the first one found:

1. `--level junior|senior|staff` passed to the skill
2. `level:` in the frontmatter of `.claude/agentic-ml.local.md` in the project root
3. `level` recorded in `<out-dir>/run-summary.json` when continuing a run
4. Otherwise:
   - `orchestrate-e2e` and `select-approach` ask once: *"How should I work with you — junior (explain and pause at every gate), senior (pause at key gates, terse), or staff (decisions and risks only)?"* Then they offer to save the answer to `.claude/agentic-ml.local.md`.
   - Other skills run standalone without asking and default to `senior`.

Record the resolved `level` in every JSON artifact (base schema field).

### Settings file

`.claude/agentic-ml.local.md` (personal; suggest adding it to `.gitignore`):

```markdown
---
level: senior
autonomy: review-key-gates   # optional; overrides the level default
---

Optional team conventions the skills should follow, e.g.
"we use conda, not uv", "MLflow tracking server: http://mlflow.internal".
```

Read the body as context. Follow environment and tooling conventions written there. Never run commands that are written there without the normal approval rules.

## What changes by level

| | `junior` | `senior` | `staff` |
|---|---|---|---|
| Explanations | Each finding gets one sentence on *why it matters* and names the pitfall (e.g. "this is target leakage"), with a link to the reference that explains it | Finding, evidence, fix — no tutorials | Summary lists only `blocker`/`high` findings; everything else stays in the artifact |
| Default autonomy | `review-every-gate` | `review-key-gates` | `autonomous` |
| Code | Writes readable, commented scaffolds into the project (e.g. `train_tabular.py`) and explains each step before running it | Works with the user's code; proposes diffs | Reviews existing code, notebooks, or PRs as an auditor; proposes minimal diffs |
| Choices | Recommends one default and says why | Top 2–3 options with trade-offs and a recommendation | Frames choices as decisions: cost, risk, owner, and what would change the call |
| Report emphasis | A "check this yourself" list of 3–5 things a reviewer should look at | Evidence and re-run commands | Decision record: risks accepted, owners, cost, rollout and monitoring |

## Autonomy

| Setting | Pauses for human review |
|---|---|
| `review-every-gate` | After every gate |
| `review-key-gates` | After the target contract and split lock (gate 1), before training spend (end of gate 5), and at promotion |
| `autonomous` | Only on `NO-GO`, `needs-approval` actions, and promotion |

Regardless of autonomy:

- Promotion always requires human sign-off.
- `needs-approval` actions always wait for approval.
- The final test-set evaluation runs once, after the user has accepted the model choice.

## Review card

Show this at every pause:

```text
Gate <n> — <name>: GO | CONDITIONAL | NO-GO
Decided: <one line>
Evidence (evidence.md § Gate <n>):
  1) <claim> — <command that shows it, and its output>
  2) ...
Assumptions: <list, or "none">
Re-run: uvx showboat --workdir <out-dir> verify <out-dir>/evidence.md
Reply "continue", or tell me what to change.
```

For `junior`, add:

```text
Why this matters: <one or two sentences>
Check this yourself: <2–3 blocks in evidence.md worth reading, and what to look for in each>
```

For `staff`, drop the evidence list to the single strongest item plus the notebook's verify status, and add `Decision needed:` when a policy call is required.

## Audit mode

When the user points a skill at existing work — a script, notebook, PR, or another run's out-dir — and asks for a review:

- Run the skill's checks against that work as a reviewer.
- Report findings with evidence.
- Propose minimal diffs instead of rewriting.

Audit mode is the default for `staff` when existing code is supplied, and available at every level.
