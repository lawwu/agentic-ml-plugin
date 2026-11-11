---
name: build-review-page
description: Build one-minute HTML review pages that let a person check an agent's ML work at a gate. Each page answers one question (what am I approving, what is predicted and when, is the split leak-free, does it beat the baseline, where is it wrong, what does the cutoff cost, what else was tried) and binds every number to a field of a skill's JSON artifact, which a script then checks. Use at any review pause, before asking for approval or sign-off, or when asked for a review page, a one-pager, a gate summary, or something a human can use to validate the run.
argument-hint: "[--page decision|label|split|baseline|errors|value|tried|all] [--gate N] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Build Review Page

Turn a run's JSON artifacts into pages a person can read in about a minute and answer. Each page asks the reviewer for the judgments the artifacts cannot make, and a script proves the page says what the artifacts say.

These pages are for the person approving a gate. They are not the run browser (`report.html` from `orchestrate-e2e`) or the stakeholder presentation (`value-demo.html` from `demonstrate-value`).

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `--page NAME` — which page to build (default: `decision`); `all` builds every page whose sources exist
- `--gate N` — the gate under review, for the `decision` page (default: the latest gate with an artifact)
- `--out-dir DIR` — the run folder holding the artifacts (default: `./reports/e2e-run`)
- `--run-id ID` — run ID shared across orchestrated skills

Target: `$ARGUMENTS`

## The pages

| Page | The question it answers | Built from | First available |
|---|---|---|---|
| [decision](references/pages/decision.md) | What am I approving, and why? | the gate's artifacts, `run-summary.json` | any gate |
| [label](references/pages/label.md) | What is predicted, and when is the truth known? | `review-target.json` | gate 1 |
| [split](references/pages/split.md) | Why can't the test rows have informed the model? | `review-target.json`, `splits/split-manifest.json`, `check-data-pipeline.json` | gate 1 |
| [baseline](references/pages/baseline.md) | Is it better than the simple alternative, beyond noise? | `build-baseline.json`, `check-eval.json` | gate 3 |
| [errors](references/pages/errors.md) | Where is it wrong? | `check-eval.json`, `explain-model.json` | gate 7 |
| [value](references/pages/value.md) | What does acting at this cutoff cost and gain? | `check-eval.json`, `demonstrate-value.json` | gate 7 |
| [tried](references/pages/tried.md) | What else was tried, and how many looks were taken? | `select-approach.json`, `plan-experiment.json`, `train-model.json` | gate 4 |

Read the page's reference file before building it. It lists the fields to show, the picture to draw, the questions only a person can answer, and the conditions that must appear under "Distrust this if".

## Rules for every page

1. **One question, answered in the headline.** The `<h1>` is the answer in one sentence, not a title.
2. **The reader is new to this model and has a minute.** Plain words. The first time a metric appears, say what it measures and what a bad value looks like, in one clause.
3. **Read JSON only.** Use the artifacts in `<out-dir>` and the JSON files they point to (`split-manifest.json`, `eval-metrics-*.json`, `data-contract.json`). Never open data, prediction, or model files to build a page. This keeps the page inside the [evaluation protocol](../../references/evaluation-protocol.md).
4. **Bind every number.** A number from an artifact is written as `<span data-ref="check-eval.json#/results/0/score" data-fmt=".3f">0.782</span>`. The path after `#` is a JSON pointer. `data-fmt` is a Python format spec; leave it out and the checker accepts the value rounded to the decimals you show.
5. **Do no arithmetic.** If no artifact holds the number, the page does not show it. Say what is missing and which skill would produce it. The only exception is counting the items of a list you bind ("3 slices flagged").
6. **Declare what is not from an artifact.** A constant the reader needs (a regulatory threshold, a conventional cutoff) is written as `<span data-literal="four-fifths rule">0.8</span>`. Use this rarely.
7. **Show the artifact's decision.** The decision chip is bound to the artifact's `decision`. Never soften a `NO-GO` or `CONDITIONAL` in the headline.
8. **One large picture.** Draw it from the bound fields with the row classes in `assets/base.html` (a name, a track, a value per row), so labels stay readable on a phone. Draw an interval wherever the artifact has one. Put names and values on the rows, bound like any other number, not in a legend. Mark the chart `data-chart` with a `data-ref` to the array or object it draws and an `aria-label` saying what it shows. Use inline SVG only for a shape rows cannot make, and never with text that shrinks below 12 px on a phone. If one number answers the question, show the number large and draw nothing.
9. **Ask for one to five judgments.** Each is something the reviewer knows and the artifacts cannot: whether the label is the event the business acts on, whether a slice matters, whether an assumption is still true. Never "does this look right?".
10. **Say when to distrust the page.** Test each condition in the reference file against the artifacts and list the ones that hold. When none hold, say how many were tested and name the largest remaining risk.
11. **Missing source, no page.** If a required artifact or field is absent, do not build the page from memory or from the conversation. Record it under `omitted` with the reason.
12. **Make every claim citable.** Give each fact and each distrust item a `data-claim` tag: the page's letter and a number (`B1`, `B2`).
13. **Stay under 350 words,** not counting the chart and the sources line. Detail stays in the artifact.
14. **One self-contained file:** inline CSS, no outside fonts, scripts, or images, readable on a phone and in dark mode.

Start from [assets/base.html](assets/base.html) and keep its block order: decision, picture, facts, ask, distrust, sources. Colors, type, and the chart are yours to design for the subject. The `decision` page links to the other pages that exist (`<a href="baseline.html">`).

## Your responsibilities

### 1. Choose the pages

List the artifacts in `<out-dir>`. For `--page all`, build each page whose required sources exist. At a review pause, build what the level calls for (see below).

### 2. Build each page

Copy `assets/base.html` to `<out-dir>/review/<page>.html` and fill it by following the page's reference file. Take text fields (the label formula, a finding's title, a caveat) from the artifact and bind them too.

### 3. Stamp and check

```bash
uv run "${CLAUDE_SKILL_DIR}/scripts/check_page.py" <out-dir>/review/<page>.html --stamp
uv run "${CLAUDE_SKILL_DIR}/scripts/check_page.py" <out-dir>/review/<page>.html --strict
```

`--stamp` writes the sha256 of each artifact the page reads into the page. The check then fails when:

- a shown value differs from its artifact field, or the field does not exist
- an artifact changed after the page was stamped
- a number is neither bound nor declared
- a block is missing, the ask has no items or more than five, or no claim is tagged
- the page loads anything from outside itself, lacks a title, language, viewport, or image labels, or is over the word limit

If the check fails, fix the page and run it again. Never edit an artifact to make a page pass. If it still fails after two repairs, do not give the page to the reviewer; report the errors.

The checker confirms that a chart's `data-ref` field exists. It cannot confirm the drawing matches the data, so tell the reviewer the picture is unchecked when a chart carries the argument.

### 4. Look at it

Open each page in a browser when one is available. Check it at phone width (about 375 px): no sideways scrolling, the headline and decision visible without scrolling, no chart text under 12 px, no labels overlapping. Check dark mode. Record `browser_verified`. If no browser is available, say the layout was not looked at.

### 5. Hand it to the reviewer

Give the path to the `decision` page and the questions from its ask block. When the reviewer replies, append one line per comment to `<out-dir>/review/responses.jsonl`:

```json
{"page": "baseline", "claim": "B2", "verdict": "accepted | changes-requested | rejected", "comment": "<their words>", "reviewer": "<name>", "at": "<ISO-8601 UTC>", "page_sha256": "<sha256 of the page they read>"}
```

Record the reviewer's words, not a summary. A `changes-requested` or `rejected` claim goes back to the skill that owns the artifact: rerun it, then rebuild and re-check the page. Never change a number on a page by hand. A reply is not an approval of the gate; approval follows the run's normal rules.

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

Every page is written for a newcomer whatever the level, and every page passes the same check. Level changes which pages you build at a pause:

- **junior:** every available page; walk through each ask item in the conversation
- **senior:** `decision`, plus each page whose source artifacts changed at this gate
- **staff:** `decision`, plus the page for any artifact with a `blocker` or `high` finding

### Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- one `exec` block per page running `check_page.py <page> --strict` (by absolute script path), so `showboat verify` fails if a page or its artifacts change after review
- the sha256 of each page

If showboat is unavailable, follow the fallback in the evidence-notebook reference and record each check's output by hand.

### JSON artifact

Write `build-review-page.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` when every requested page passed its check; `CONDITIONAL` when a requested page was omitted for a missing source; `NO-GO` when a page failed its check and must not be shown to a reviewer. This decision is about the pages, not the model.
- `pages`: one entry per page with `path`, `sha256`, `sources`, the checker's counts (`check`), and `browser_verified`
- `omitted`: each page not built, with the reason
- `entry_page`, `responses_path`
- `findings`: one per failed check (`high`) and per omitted page (`medium`)

`provenance` is omitted: this skill reads only other artifacts.

## Example session

```
/agentic-ml:build-review-page --page all --out-dir ./reports/run-001

Artifacts in ./reports/run-001: review-target, check-dataset-quality, build-baseline, plan-experiment,
  check-data-pipeline, train-model, check-eval, explain-model

decision.html   PASS  188 words, 9 values checked     browser: ok
label.html      PASS  241 words, 11 values checked    browser: ok
split.html      PASS  203 words, 12 values checked    browser: ok
baseline.html   PASS  214 words, 13 values checked    browser: ok
errors.html     PASS  262 words, 17 values checked    browser: ok
tried.html      PASS  197 words, 8 values checked     browser: ok
value           omitted: check-eval.json has no operating_point (run check-eval with a threshold)

Start here: ./reports/run-001/review/decision.html
The reviewer is asked 4 things on that page; baseline.html flags B3 (the gain's interval touches zero).
Artifact: ./reports/run-001/build-review-page.json  (CONDITIONAL: 1 page omitted)
```

## Additional resources

- [assets/base.html](assets/base.html) — the page skeleton
- [scripts/check_page.py](scripts/check_page.py) — the binding, freshness, and length check
- [references/pages/](references/pages/) — what each page must show
- [../../references/schemas.md](../../references/schemas.md) — the artifacts the pages read
- [effective-html](https://github.com/plannotator/effective-html) — the one-pager idea these pages apply to ML review
