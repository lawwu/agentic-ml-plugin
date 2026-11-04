---
name: demonstrate-value
description: Create a visual presentation demonstrating business value of a trained model, with every figure recorded in the run's showboat evidence notebook so it can be re-run and checked. Use after evaluation and explainability to synthesize findings into a stakeholder-ready demo. Invoke when asked to show business value, create a model presentation, generate a demo, or produce a stakeholder report.
argument-hint: "[--model PATH] [--eval-results PATH] [--explain-results PATH] [--baseline PATH] [--business-context TEXT] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Demonstrate Value

Synthesize evaluation, explainability, and baseline results into a stakeholder-ready business value presentation. Every figure is recorded with the command that produced it in the run's evidence notebook ([showboat](https://github.com/simonw/showboat)), so a reviewer can re-run it.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `--model PATH` — path to the trained model or checkpoint
- `--eval-results PATH` — path to `check-eval.json` (default: `<out-dir>/check-eval.json`)
- `--explain-results PATH` — path to `explain-model.json` (default: `<out-dir>/explain-model.json`)
- `--baseline PATH` — path to `build-baseline.json` (default: `<out-dir>/build-baseline.json`)
- `--business-context TEXT` — plain-language description of the business problem and stakes (e.g., "fraud detection for a $2B/year card portfolio")
- `--out-dir DIR` — output directory for artifacts (default: `./reports/e2e-run`)
- `--run-id ID` — run ID shared across orchestrated skills

Target: `$ARGUMENTS`

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- The presentation is written for stakeholders at every level; the level only changes the note to the data scientist.

## Your responsibilities

### 1. Gather inputs

Load available inputs from `--out-dir` or explicit paths:

- `check-eval.json` — model scores, baseline deltas, regressions
- `explain-model.json` — top features, bias audit results, caveats
- `build-baseline.json` — non-ML baseline performance floor
- `--business-context` — use to frame metrics in business terms

If none of the JSON artifacts are available, ask for at least `--eval-results` before proceeding. Proceed with partial data if some artifacts are missing — note which sections are omitted.

### 2. Translate metrics into business terms

Convert model metrics into business impact **from an operating point**, never from a ranking metric alone. AUPRC, ROC-AUC, and NDCG summarize performance across all thresholds; they do not say how many cases a deployed model catches.

To state counts or money:

1. Take the decision threshold and the precision/recall (or confusion matrix) at that threshold on held-out data — from `check-eval.json`, or compute it from saved predictions.
2. Do the arithmetic explicitly. For classification: cases caught per period = volume × base rate × recall; false alarms = cases flagged × (1 − precision).
3. Label every input as **measured** (from an artifact), **user-provided** (from `--business-context`), or **assumed**. List every assumption in the presentation and in the JSON artifact.

Examples:

- Classification: "At the chosen threshold, recall rose from 0.41 (rule-based baseline) to 0.63 on held-out data → at 50,000 transactions/day (user-provided) and a 0.3% fraud rate (measured), about 33 more fraud cases caught per day (50,000 × 0.003 × 0.22)."
- Regression: "MAE fell from $42K to $34K per SKU on the held-out quarter → forecast error drops by ~$8K per SKU."

If no operating point is available, describe the impact directionally ("catches more fraud at the same review volume") and say what is missing. Do not invent counts or dollar figures.

### 3. Record the evidence in the run notebook

Every figure in the presentation must appear in the run's evidence notebook, `<out-dir>/evidence.md`, next to the command that produced it, so `showboat verify` can re-run it. Follow [../../references/evidence-notebook.md](../../references/evidence-notebook.md). Create the notebook with `showboat init` if this skill runs standalone.

```bash
uvx showboat --workdir <out-dir> note <out-dir>/evidence.md "## demonstrate-value
Business impact at the operating point chosen on val."
uvx showboat --workdir <out-dir> exec <out-dir>/evidence.md bash "python3 value_calc.py"
```

- Put the business-impact arithmetic in `<out-dir>/value_calc.py`. It reads the artifact JSON files, prints each input with its label (measured / user-provided / assumed), and prints each result. Run it through `showboat exec` so the calculation is recorded and re-runnable.
- Add a note for each presentation section's narrative only when it states a number not already in the notebook, and back that number with an `exec` block.
- Run `uvx showboat --workdir <out-dir> verify <out-dir>/evidence.md` last. It exits non-zero if any recorded output changed; report that instead of hiding it.

If showboat cannot run, follow the fallback in the evidence-notebook reference, and say the figures are not verified.

### 4. Presentation sections

Cover these sections in the presentation:

1. **Problem** — business context, what decisions the model supports, current pain points
2. **Baseline** — non-ML baseline performance; what the status quo looks like
3. **Model Performance** — primary metric, delta over baseline, pass/fail against threshold
4. **Key Drivers** — top 3–5 features from explainability, what they mean in business terms
5. **Business Impact** — estimated value (cost savings, revenue, risk reduction) in a table, with each input labeled measured / user-provided / assumed
6. **Risks and Caveats** — bias findings, known failure modes, deployment conditions
7. **Recommendation** — restate the run's actual decision (from `run-summary.json`, or from `check-eval.json` and `explain-model.json` when run standalone) for a non-technical audience. Never upgrade it: a `CONDITIONAL` or `NO-GO` stays one.

Keep language non-technical. Translate terms like "precision", "F1", and "SHAP" into business equivalents, but keep every number traceable to the evidence notebook.

### 5. Write artifacts

- `<out-dir>/value_calc.py` — the business-impact calculation
- the `## demonstrate-value` section of `<out-dir>/evidence.md`
- `<out-dir>/value-demo.html` — a standalone presentation page (inline CSS, no external assets). Use only figures that appear in the evidence notebook, and link to it from the page.
- `<out-dir>/demonstrate-value.json` — structured artifact (see JSON artifact section)

Report the HTML path and the `showboat verify` result in the final output.

### JSON artifact

Write `demonstrate-value.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: always `GO` (this skill is informational and does not gate promotion)
- `model`, `business_context`, `primary_metric`, `baseline_score`, `model_score`, `improvement_delta`
- `business_impact`: array of estimated impact items (metric, description, estimated_value)
- `presentation_path`, `showboat_version`
- `evidence_notebook`, `evidence_blocks`, and `evidence_verified` (`true` only if `showboat verify` exited 0)
- `assumptions`: every non-measured input, each labeled `user-provided` or `assumed`
- `inputs_used`: paths to eval_results, explain_results, baseline_results (null if not available)

## Example session

```
/agentic-ml:demonstrate-value --business-context "card fraud review; ~50K transactions/day; avg loss $5K per missed fraud" --out-dir ./reports/run-001

Loading inputs from ./reports/run-001:
  ✓ check-eval.json — auprc=0.847; at threshold 0.32: precision=0.58, recall=0.63
  ✓ build-baseline.json — rule-based heuristic: precision=0.35, recall=0.41
  ✓ explain-model.json — top features: transaction_amount_zscore, merchant_category, hour_of_day
  ✓ run-summary.json — decision: CONDITIONAL (bias caveat on ip_country)

Business impact (value_calc.py, recorded with showboat exec):
  volume = 50,000/day            [user-provided]
  fraud rate = 0.3%              [measured: check-dataset-quality.json]
  recall gain = 0.63 − 0.41      [measured: check-eval.json, build-baseline.json]
  → ~33 more fraud cases caught per day
  avg loss per case = $5K        [user-provided]
  → ~$165K/day in prevented losses (before review costs)

showboat verify ./reports/run-001/evidence.md → all outputs match

Presentation: ./reports/run-001/value-demo.html  (recommendation shown as CONDITIONAL)
Evidence: ./reports/run-001/evidence.md (## demonstrate-value)
Artifact: ./reports/run-001/demonstrate-value.json
```

## Additional resources

- [showboat](https://github.com/simonw/showboat) — executable Markdown documents that record commands with their output, plus `verify` to re-run them
- [check-eval](../check-eval/SKILL.md) — evaluation results (primary input)
- [explain-model](../explain-model/SKILL.md) — explainability and bias (secondary input)
- [build-baseline](../build-baseline/SKILL.md) — non-ML baseline (comparison floor)
- [../../references/schemas.md](../../references/schemas.md) — JSON artifact schema
