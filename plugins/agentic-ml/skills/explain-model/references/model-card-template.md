# Model Card Template

Based on Mitchell et al. 2019 — "Model Cards for Model Reporting" (https://arxiv.org/abs/1810.03993).

Use this template as the output target for `explain-model`. Fill all required sections before promotion.

---

```markdown
# Model Card: <Model Name>

## 1. Model Details

- **Model name**: <name and version>
- **Model type**: <architecture, e.g., XGBoost classifier, LLaMA 7B fine-tuned>
- **Training date**: <YYYY-MM-DD>
- **Model version**: <semantic version or checkpoint ID>
- **License**: <license>
- **Contact**: <team or owner>

**Links**:
- Checkpoint: <path or HF Hub link>
- Experiment tracking: <W&B / MLflow run URL>
- Code: <git commit or repo link>

---

## 2. Intended Use

**Primary intended use**:
<One paragraph describing the primary use case, the decision this model supports, and the deployment context.>

**Primary intended users**:
<Who will use this model or its outputs (internal team, downstream service, end users).>

**Out-of-scope uses**:
- <Use case 1 that the model should NOT be used for and why>
- <Use case 2>

---

## 3. Factors

**Relevant factors**:
<Describe groups, sub-populations, or environmental conditions that affect model performance.>

- Demographics: <age, gender, geography, etc. if relevant>
- Instrumentation: <device types, platforms, data sources>
- Environment: <operating conditions, time periods>

**Evaluation factors**:
<Which factors were disaggregated in evaluation and why.>

---

## 4. Metrics

**Primary metric**: <metric name and definition>
**Secondary / guardrail metrics**:
- <metric>: threshold = <value>

**Promotion threshold**: <primary metric value required to promote>

**Decision threshold policy** (for probabilistic outputs):
<How the score is converted to a decision; whether threshold is fixed or calibrated.>

---

## 5. Evaluation Data

- **Dataset**: <name or path>
- **Size**: <N rows, M features>
- **Split**: <validation / holdout / test>
- **Preprocessing**: <key steps applied>
- **Representativeness**: <how well the eval data reflects production distribution>

---

## 6. Training Data

- **Dataset summary**: <high-level description; no PII>
- **Size**: <N rows, M features, time range>
- **Label source**: <how labels were generated>
- **Known gaps or biases in training data**:
  - <gap 1>
  - <gap 2>

---

## 7. Quantitative Analysis

### Overall performance

| Metric | Value |
|--------|-------|
| <primary metric> | <value> |
| <secondary metric> | <value> |

### Disaggregated performance

<For each relevant factor / protected attribute, report metrics.>

| Subgroup | Primary metric | Secondary metric | N |
|----------|---------------|-----------------|---|
| <group>  | <value>       | <value>         | <N> |

### Bias / fairness metrics

| Attribute | Metric | Value | Threshold | Status |
|-----------|--------|-------|-----------|--------|
| <attr>    | disparate impact | <val> | ≥ 0.8 | PASS/FAIL |

---

## 8. Ethical Considerations

<Describe potential harms, misuse risks, and mitigation strategies.>

- **Potential harms**: <list>
- **Mitigation steps taken**: <list>
- **Residual risks**: <list>
- **Recommended monitoring**: <what to track in production>

---

## 9. Caveats and Recommendations

**Known limitations**:
- <limitation 1>
- <limitation 2>

**Recommendations for users**:
- <recommendation 1>
- <recommendation 2>

**Recommended follow-up**:
- <next evaluation, audit, or retraining trigger>
```

---

## Section Guidance

### Section 2: Intended Use
Be specific about what this model should NOT do. Misuse of ML models often comes from use cases never explicitly ruled out. Err on the side of explicit exclusions.

### Section 3: Factors
List every group for which performance may differ. If you did not evaluate on a subgroup, say so explicitly — absent evaluation is not the same as absent risk.

### Section 7: Quantitative Analysis
Disaggregated performance is the most actionable section. If you cannot report it, explain why (e.g., protected attributes not available in holdout data) and flag this as a risk.

### Section 8: Ethical Considerations
Do not skip this section even for "low-risk" models. Require explicit sign-off from a responsible person before promotion.

### Section 9: Caveats
Include retraining triggers (data drift thresholds, performance degradation thresholds). Model cards should be living documents updated at each promotion.
