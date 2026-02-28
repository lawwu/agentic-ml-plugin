# Interpretability Methods

Reference for `explain-model`. Use this guide to select the right importance method and understand trade-offs.

---

## Method Selection Matrix

| Model type | Recommended method | Fallback |
|------------|-------------------|---------|
| Tree ensemble (RF, XGBoost, LightGBM) | SHAP `TreeExplainer` | Built-in `feature_importances_` |
| Linear / logistic regression | Coefficients (standardized) | Permutation |
| Neural network (MLP, Transformer) | SHAP `DeepExplainer` or `GradientExplainer` | Permutation |
| SVM / kernel methods | Permutation | SHAP `KernelExplainer` (slow) |
| Black-box / ensemble stacking | Permutation | SHAP `KernelExplainer` |
| Probabilistic / Bayesian | Permutation | SHAP `KernelExplainer` |

**Default (`auto`)**: use SHAP if model is tree or neural network; permutation otherwise.

---

## SHAP (SHapley Additive exPlanations)

**What it measures**: each feature's marginal contribution to a prediction, averaged over all feature orderings (Shapley values from cooperative game theory).

**Pros**:
- theoretically grounded (efficiency, symmetry, dummy, additivity properties)
- consistent: if a model relies more on a feature, SHAP value increases
- supports both global (mean |SHAP|) and local (per-instance) explanations
- `TreeExplainer` is O(TLD²) — fast for trees

**Cons**:
- `KernelExplainer` is O(N²) — slow for large datasets/many features
- correlated features share SHAP mass, making individual attribution ambiguous
- `DeepExplainer` requires background dataset; results vary with background choice

**When to use**:
- tree ensembles: always prefer `TreeExplainer`
- neural networks with tabular input: `DeepExplainer` or `GradientExplainer`
- any model where you need local + global explanations

**Code pattern**:
```python
import shap
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_val)
shap.summary_plot(shap_values, X_val)
```

---

## Permutation Importance

**What it measures**: drop in model performance when a feature's values are randomly shuffled, breaking its relationship with the target.

**Pros**:
- model-agnostic: works with any sklearn-compatible model
- directly tied to evaluation metric (you choose the metric)
- detects features that are useless even if correlated with others

**Cons**:
- can be misleading with correlated features (both may appear unimportant when either alone is sufficient)
- requires re-running inference N × num_features times — slow for large models
- results depend on the evaluation split used

**When to use**:
- when no SHAP explainer is available for the model type
- as a cross-validation check against SHAP (disagreement → correlated features)
- when you need metric-tied importance (e.g., "how much does removing this feature hurt F1?")

**Code pattern**:
```python
from sklearn.inspection import permutation_importance
result = permutation_importance(model, X_val, y_val, n_repeats=10, scoring='f1')
```

---

## Built-in Feature Importance

**What it measures**: model-specific internal importance signals.

| Model | Built-in signal | How computed |
|-------|----------------|--------------|
| Random Forest | `feature_importances_` | Mean decrease in impurity (MDI) |
| XGBoost | `feature_importances_` | Gain / cover / frequency |
| LightGBM | `feature_importances_` | Gain or split count |
| Linear/Logistic | `coef_` | Coefficient magnitude |
| Decision tree | `feature_importances_` | MDI |

**Pros**:
- zero inference overhead — computed during training
- very fast

**Cons**:
- MDI is biased toward high-cardinality features
- not directly comparable across model types
- does not account for correlated features
- XGBoost `gain` and `frequency` can give very different rankings

**When to use**:
- as a quick first pass before running SHAP
- when dataset is too large for SHAP/permutation
- as a sanity check against SHAP results

---

## Partial Dependence Plots (PDP) and ICE

**PDP**: shows the marginal effect of one or two features on the predicted outcome, averaged over all other features.

**ICE (Individual Conditional Expectation)**: shows the same effect for individual instances — reveals heterogeneity hidden by PDP averaging.

**Key shapes to recognize**:

| Shape | Meaning |
|-------|---------|
| Monotonically increasing | Feature positively associated with target |
| Monotonically decreasing | Feature negatively associated with target |
| Non-monotonic (U or inverted U) | Interaction effects; investigate further |
| Step function | Threshold or discretized feature |
| Flat | Feature has no effect (consider removing) |
| High ICE variance | Strong interaction with other features |

**Code pattern**:
```python
from sklearn.inspection import PartialDependenceDisplay
PartialDependenceDisplay.from_estimator(model, X_val, features=[0, 1, 2])
```

---

## SHAP vs Permutation: When They Disagree

If SHAP and permutation rankings diverge by > 2 positions in the top 10:

1. Check for correlated feature groups using `df.corr()` or VIF
2. Apply grouped permutation importance (permute the entire correlated group)
3. Report both rankings and note the discrepancy — do not silently pick one

**Actionable rule**: if feature A and feature B are correlated (r > 0.7) and their combined permutation importance is high but individual importances are low, they form a redundant group. Report as a group.

---

## Bias / Fairness Metric Reference

| Metric | Formula | Interpretation |
|--------|---------|----------------|
| Disparate impact ratio | `min(P(Ŷ=1|G=g)) / max(P(Ŷ=1|G=g))` | < 0.8: adverse impact (4/5 rule) |
| Demographic parity difference | `max_g P(Ŷ=1|G=g) - min_g P(Ŷ=1|G=g)` | > 0.1: warning |
| Equalized odds (TPR parity) | `max_g TPR_g - min_g TPR_g` | > 0.1: warning; > 0.2: blocker |
| Predictive parity (PPV parity) | `max_g PPV_g - min_g PPV_g` | > 0.1: warning |
| Calibration gap | Max difference in calibration curves across groups | > 0.05: warning |

Use `fairlearn` or manual computation:
```python
from fairlearn.metrics import demographic_parity_ratio, equalized_odds_difference
```
