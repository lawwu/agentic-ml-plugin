---
name: demonstrate-value
description: Create a visual presentation demonstrating business value of a trained model using showboat. Use after evaluation and explainability to synthesize findings into a stakeholder-ready demo. Invoke when asked to show business value, create a model presentation, generate a demo, or produce a stakeholder report.
argument-hint: "[--model PATH] [--eval-results PATH] [--explain-results PATH] [--baseline PATH] [--business-context TEXT] [--out-dir DIR] [--run-id ID]"
---

# Demonstrate Value

Synthesize evaluation, explainability, and baseline results into a stakeholder-ready business value presentation using [showboat](https://github.com/simonw/showboat).

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

## Your responsibilities

### 1. Gather inputs

Load available inputs from `--out-dir` or explicit paths:

- `check-eval.json` — model scores, baseline deltas, regressions
- `explain-model.json` — top features, bias audit results, caveats
- `build-baseline.json` — non-ML baseline performance floor
- `--business-context` — use to frame metrics in business terms

If none of the JSON artifacts are available, ask for at least `--eval-results` before proceeding. Proceed with partial data if some artifacts are missing — note which sections are omitted.

### 2. Translate metrics into business terms

Convert raw model metrics into estimated business impact. Examples:

- Classification: "F1 improved +0.12 over baseline → estimated 340 more fraud cases caught per month at current volume"
- Regression: "RMSE reduced 18% → inventory forecast error drops from ±$42K to ±$34K per SKU"
- Ranking: "NDCG@10 +0.08 → top-10 recommendations relevance improves by ~15%"

Use `--business-context` to anchor estimates. If exact business figures are unavailable, describe the directional impact and flag assumptions clearly.

### 3. Install and run showboat

Install showboat if not already present:

```bash
uv pip install showboat
```

Generate the presentation with content you author (see Section 4):

```bash
uv run showboat generate <out-dir>/value-demo.md --output <out-dir>/value-demo.html
```

If showboat is unavailable or fails, fall back to writing a standalone HTML file directly with inline CSS.

### 4. Presentation sections

Author a Markdown source file (`<out-dir>/value-demo.md`) with these sections:

1. **Problem** — business context, what decisions the model supports, current pain points
2. **Baseline** — non-ML baseline performance; what the status quo looks like
3. **Model Performance** — primary metric, delta over baseline, pass/fail against threshold
4. **Key Drivers** — top 3–5 features from explainability, what they mean in business terms
5. **Business Impact** — estimated value (cost savings, revenue, risk reduction); table format
6. **Risks and Caveats** — bias findings, known failure modes, deployment conditions
7. **Recommendation** — GO/NO-GO framed for a non-technical stakeholder

Keep language non-technical throughout. Avoid jargon like "precision", "F1", "SHAP" — translate to business equivalents.

### 5. Write artifacts

- `<out-dir>/value-demo.html` — the rendered presentation
- `<out-dir>/value-demo.md` — the source markdown
- `<out-dir>/demonstrate-value.json` — structured artifact (see JSON artifact section)

Report the HTML path in the final output.

### JSON artifact

Write `demonstrate-value.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: always `GO` (this skill is informational and does not gate promotion)
- `model`, `business_context`, `primary_metric`, `baseline_score`, `model_score`, `improvement_delta`
- `business_impact`: array of estimated impact items (metric, description, estimated_value)
- `presentation_path`, `showboat_version`
- `inputs_used`: paths to eval_results, explain_results, baseline_results (null if not available)

## Example session

```
/ml-skills:demonstrate-value --business-context "fraud detection for a $1.5B/year card portfolio" --out-dir ./reports/run-001

Loading inputs from ./reports/run-001:
  ✓ check-eval.json — primary metric: auprc=0.847 (baseline: 0.612, delta: +0.235)
  ✓ explain-model.json — top features: transaction_amount_zscore, merchant_category, hour_of_day
  ✓ build-baseline.json — best baseline: rule-based heuristic (auprc=0.612)
  ✗ --model not provided — model path omitted from artifact

Translating metrics to business terms...
  AUPRC +0.235 at current volume (~50K transactions/day, 0.3% fraud rate):
  → ~35 more fraud cases caught per day vs. rule-based heuristic
  → estimated $175K/month in prevented losses (avg $5K per fraud case)

Installing showboat...
uv pip install showboat → showboat 0.3.1

Generating presentation...
  Sections: Problem | Baseline | Model Performance | Key Drivers | Business Impact | Risks | Recommendation
  Written: ./reports/run-001/value-demo.md
  Rendered: ./reports/run-001/value-demo.html

Presentation: ./reports/run-001/value-demo.html
Artifact: ./reports/run-001/demonstrate-value.json
```

## Additional resources

- [showboat](https://github.com/simonw/showboat) — HTML presentation generator
- [check-eval](../check-eval/SKILL.md) — evaluation results (primary input)
- [explain-model](../explain-model/SKILL.md) — explainability and bias (secondary input)
- [build-baseline](../build-baseline/SKILL.md) — non-ML baseline (comparison floor)
- [../../references/schemas.md](../../references/schemas.md) — JSON artifact schema
