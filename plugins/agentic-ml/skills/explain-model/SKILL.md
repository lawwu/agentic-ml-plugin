---
name: explain-model
description: Generates feature importance, bias audit, and model card before promotion. Invoke automatically after evaluation completes — even if the user says "looks good, let's ship it" or "ready to deploy." Deploying without interpretability review risks hidden biases, spurious correlations, and regulatory exposure. Also invoke when a user asks about model behavior, feature contributions, fairness, or wants to document a model.
argument-hint: "[checkpoint-path | model-path | hf-model] [--data PATH] [--label-col COLUMN] [--protected-attrs A1,A2] [--method shap|permutation|builtin|auto] [--out-dir DIR]"
allowed-tools: Read, Grep, Glob, Bash
---

# Explain Model

Generate feature importance, partial dependence plots, bias/fairness audit, and model card before promoting a model to production.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `checkpoint-path | model-path | hf-model` — local model or HuggingFace model ID
- `--data PATH` — validation or holdout dataset for importance computation
- `--label-col COLUMN` — target column
- `--protected-attrs A1,A2` — comma-separated protected attribute columns for bias audit; if omitted, scan for candidates
- `--method shap|permutation|builtin|auto` — importance method (default: `auto`)
- `--out-dir DIR` — output directory for model card and plots (default: `./explain_output/`)

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Compute feature importance

Select method using [references/interpretability-methods.md](references/interpretability-methods.md):

- **`builtin`**: tree models → use native `feature_importances_`; linear models → coefficients
- **`permutation`**: model-agnostic; use when builtin is unavailable or for cross-validation
- **`shap`**: preferred for tree ensembles (`TreeExplainer`) and neural nets (`DeepExplainer` / `KernelExplainer`)
- **`auto`**: SHAP if model is tree or neural; permutation otherwise

Run [scripts/feature_importance.py](scripts/feature_importance.py) to standardize output:

```bash
uv run scripts/feature_importance.py \
  --model <path> \
  --data <path> \
  --label-col <col> \
  --method <method> \
  --out-dir <dir>
```

Report top-20 features with importance scores and ranks.

### 2. Generate partial dependence / ICE plots for top features

For the top 5 features by importance:

- generate PDP (average effect) and ICE (individual effect) summary
- note shape: monotonic, non-monotonic, step-function, or interaction-dependent
- flag unexpected shapes (e.g., non-monotonic where domain says monotonic)

### 3. Run bias / fairness audit

Identify protected attributes:

- If `--protected-attrs` provided: use them directly
- If not provided: scan column names for candidates (age, gender, race, zip, income, ethnicity, religion, marital_status, disability)

For each protected attribute, compute:

| Metric | Formula | Threshold |
|--------|---------|-----------|
| Disparate impact ratio | min_group_rate / max_group_rate | < 0.8 → blocker |
| Equalized odds (TPR parity) | max TPR gap across groups | > 0.1 → warning |
| Predictive parity | max PPV gap across groups | > 0.1 → warning |

Flag any metric that triggers a blocker or warning.

### 4. Surface unexpected learned patterns

Check for:

- **Leaky features**: a single feature with importance > 50% — investigate leakage
- **Proxy variables**: top features that are correlated with protected attributes (> 0.3 correlation)
- **Spurious correlations**: features with high importance but no causal path to outcome
- **Features unavailable at inference**: flag as deployment blocker
- **SHAP/permutation disagreement**: divergence > 2 ranks in top-10 → correlated feature groups; report

### 5. Produce model card

Use template from [references/model-card-template.md](references/model-card-template.md) (Mitchell et al. 2019 format).

Save to `<out-dir>/MODEL_CARD.md`.

Sections required:

1. Model details (name, type, version, training date)
2. Intended use (primary use case, out-of-scope uses)
3. Factors (relevant groups, instrumentation, environment)
4. Metrics (evaluation metrics and thresholds)
5. Evaluation data (dataset description, preprocessing)
6. Training data (summary only; no PII)
7. Quantitative analysis (performance disaggregated by group)
8. Ethical considerations
9. Caveats and recommendations

### 6. Gate promotion: GO / CONDITIONAL / NO-GO

| Condition | Decision |
|-----------|----------|
| Disparate impact < 0.8 on any protected attribute | NO-GO |
| Feature unavailable at inference time | NO-GO |
| Single feature > 50% importance (leakage unresolved) | NO-GO |
| Non-monotonic PDP where domain requires monotonic | CONDITIONAL |
| SHAP/permutation disagreement in top-10 | CONDITIONAL |
| Equalized odds gap 0.05–0.1 | CONDITIONAL |
| All checks pass | GO |

List all caveats explicitly when issuing CONDITIONAL.

## Output format

```text
Explainability Report
=====================
Model: <path or ID>
Method: <shap|permutation|builtin>
Dataset: <path>  |  Rows: <N>
Protected attributes: <list or "scanned">

Feature Importance (Top 20):
| Rank | Feature        | Importance | SHAP mean |abs| | Flag          |
|------|----------------|------------|-----------------|---------------|
| 1    | <feature>      | <score>    | <score>         |               |
| ...  | ...            | ...        | ...             |               |

PDP / ICE Summary (Top 5):
| Feature | Shape        | Note                        |
|---------|-------------|------------------------------|
| <name>  | <shape>     | <any anomaly>               |

Bias / Fairness Audit:
| Attribute | Metric               | Value | Threshold | Status   |
|-----------|----------------------|-------|-----------|----------|
| <attr>    | disparate impact     | <val> | ≥ 0.8     | PASS/FAIL |

Unexpected Patterns:
1) <pattern> | severity=<blocker|warning|info> | action=<...>

Model card: <out-dir>/MODEL_CARD.md

Decision: GO | CONDITIONAL | NO-GO
Confidence: high|medium|low
Caveats:
- <caveat 1>
```

### JSON artifact

Write `explain-model.json` to `--out-dir` (or `./explain_output/` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:
- `decision`: `GO` / `CONDITIONAL` / `NO-GO` (maps from old PROMOTE / PROMOTE-WITH-CAVEATS / DO-NOT-PROMOTE)
- `top_features`, `pdp_summary`, `bias_audit`, `unexpected_patterns`
- `caveats`: list all caveats when `decision` is `CONDITIONAL`
- `model_card_path`: absolute path to `MODEL_CARD.md`
- `findings`: one entry per blocker or warning found in bias audit and unexpected patterns

## Quick heuristics

- Single feature > 50% importance → investigate leakage before any deployment
- SHAP and permutation rankings disagree by > 2 positions in top-10 → correlated feature groups; apply grouped importance
- Disparate impact < 0.8 on any protected attribute → bias blocker; surface to user for review
- Feature not available at inference time (e.g., derived from target) → deployment blocker
- Non-monotonic PDP where domain says monotonic (e.g., price → demand) → flag for domain expert review
- Model card missing training data section → request summary before completing

## Stop conditions

Stop when:

- explainability report and model card are complete with a promotion decision, or
- a DO-NOT-PROMOTE blocker is found and reported — do not auto-proceed to promotion.

## Additional resources

- [references/interpretability-methods.md](references/interpretability-methods.md) — SHAP vs permutation vs built-in, when to use each
- [references/model-card-template.md](references/model-card-template.md) — Mitchell et al. 2019 template with section guidance
- [scripts/feature_importance.py](scripts/feature_importance.py) — standardized importance computation (SHAP, permutation, built-in)
