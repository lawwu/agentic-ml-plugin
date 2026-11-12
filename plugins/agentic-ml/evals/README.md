# Skill evals

Small cases with a known right answer, run with Claude Code's `claude plugin eval`. Each case runs the plugin in an empty, isolated workspace, and again with no plugin, so the score shows what a skill adds.

## Run

From the repository root:

```bash
claude plugin eval plugins/agentic-ml --scaffold --allow-tools Write Edit Bash --no-publish --json evals-result.json
```

```bash
uv run plugins/agentic-ml/evals/summarize.py evals-result.json
```

- `--scaffold` lets a case's `fixture.sh` seed its workspace. Read a fixture before running a suite you did not write.
- `--allow-tools` grants the tools skills need to write artifacts and run scripts. Shell commands run sandboxed, with no network.
- `--no-publish` keeps the HTML report on this machine.
- Add `--case '<glob>'` for one case (passing `--case` twice runs only the last one), `--runs 1` while editing graders (the default is 3), `--ablation none` to skip the no-plugin arm, and `--max-cost-usd N` for a spending ceiling.

Each run is a real model call on your own credential. Each of the three cases below cost about $0.63 for one run in both arms when this was written. If your shell has an `ANTHROPIC_API_KEY` that is not valid, every run fails with `Invalid API key`; run the command with `env -u ANTHROPIC_API_KEY` to use your Claude Code login.

## What a case is

```
evals/<skill>-<what-is-planted>/
├── prompt.md        the request, as a person would type it; frontmatter sets tags and limits
├── case.yaml        only when the case needs a fixture (context.scaffold_script)
├── fixture.sh       writes the fixture into the empty workspace
└── graders/*.md     one check per file
```

Rules for writing one:

1. **Plant one fact.** A leaked column, a gain inside the noise, a policy that already decides the answer. The case description says what it is.
2. **Write the twin.** For every planted case, add a clean case where the right answer is to proceed. A skill that refuses everything must not score well.
3. **Do not name the skill in the prompt.** Whether the right skill fires is part of what is measured.
4. **Grade the artifact with a regex.** Check the decision and the named finding in `<skill>.json`. The same file gets the same verdict every time.
5. **Use the model judge for one short question** a regex cannot answer, written as PASS and FAIL conditions.
6. **Add a `skill-fired` grader.** It is reported as an indicator and is not part of the score.
7. **Tag it.** First the skill name, then `planted` or `clean`, then `dev` or `holdout`.

`dev` cases are for iterating on a skill. `holdout` cases are run only to confirm a change before it merges, and their results are not used to choose what to change. Run one set with `--tag dev` or `--tag holdout`.

## Cases

| Case | Planted fact | Right answer |
|---|---|---|
| `select-approach-rule-is-enough` | A written policy already decides every invoice | `no-ml` |
| `select-approach-needs-supervised` | Twin: labeled history, no known rule | `supervised`, with a simple baseline first |
| `review-page-gain-is-noise` | The gain's interval includes zero and the evaluation said `NO-GO` | The page says the model is not shown to be better, and shows `NO-GO` |

## Reading the summary

| Column | Meaning |
|---|---|
| `with`, `without` | Mean case score with the plugin and without it, from 0 to 1 |
| `delta` | What the plugin adds |
| `planted` | Planted cases passed. A miss is a defect that got through |
| `clean` | Clean cases passed. A miss is a false alarm |
| `cost` | Dollars spent on the skill's runs, both arms |

Without the plugin the agent writes no `<skill>.json`, so the artifact graders fail in that arm and `delta` mostly measures "wrote the standard artifact". To compare judgment alone, read the model-judge grader on the reply, which is scored in both arms.

A case passes only when every scored grader passes in every run. Pass `--history plugins/agentic-ml/evals/history.jsonl` to `summarize.py` to add one line per suite run, so scores can be followed across plugin versions and models.
