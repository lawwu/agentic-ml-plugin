# Hyperparameter Search Strategies

Reference for `plan-experiment`. Use these defaults when the user has not specified HP ranges.

---

## Search Algorithm Selection

| Situation | Recommended strategy |
|-----------|---------------------|
| ≤ 5 HPs, all categorical | Grid search |
| ≤ 20 HPs, continuous ranges | Random search (50–100 trials) |
| Expensive training (> 10 min/trial) | Bayesian optimization (Optuna TPE) |
| Large candidate set, limited budget | Successive halving / Hyperband |
| Known good region from prior run | Warm-start Bayesian with previous results |

**Default**: random search with 30 trials unless budget is tight, then successive halving.

---

## HP Ranges by Model Family

### Logistic / Linear Regression

| HP | Range | Scale |
|----|-------|-------|
| `C` (regularization) | [1e-4, 1e2] | log |
| `solver` | `lbfgs`, `saga` | categorical |
| `max_iter` | 200–2000 | linear |
| `class_weight` | `None`, `balanced` | categorical |

### Decision Tree / Random Forest

| HP | Range | Scale |
|----|-------|-------|
| `n_estimators` | [50, 1000] | log-linear |
| `max_depth` | [3, 20] or `None` | linear |
| `min_samples_leaf` | [1, 50] | log |
| `max_features` | `sqrt`, `log2`, 0.5–1.0 | categorical/linear |
| `subsample` (GBM) | [0.5, 1.0] | linear |

### Gradient Boosted Trees (XGBoost / LightGBM / CatBoost)

| HP | Range | Scale |
|----|-------|-------|
| `learning_rate` | [1e-3, 0.3] | log |
| `n_estimators` | [100, 2000] | log-linear |
| `max_depth` | [3, 10] | linear |
| `subsample` | [0.5, 1.0] | linear |
| `colsample_bytree` | [0.4, 1.0] | linear |
| `reg_alpha` | [0, 10] | log |
| `reg_lambda` | [0, 10] | log |
| `min_child_weight` | [1, 20] | log |

> **Tip**: LightGBM typically needs fewer trials than XGBoost; start with 30 trials random search.

### Feedforward Neural Network (MLP / Tabular DL)

| HP | Range | Scale |
|----|-------|-------|
| `learning_rate` | [1e-4, 1e-1] | log |
| `hidden_size` | [64, 1024] | log |
| `n_layers` | [1, 6] | linear |
| `dropout` | [0.0, 0.5] | linear |
| `batch_size` | [32, 512] | log |
| `weight_decay` | [1e-6, 1e-2] | log |
| `optimizer` | `adam`, `adamw`, `sgd` | categorical |

### Transformer (Fine-tuning)

| HP | Range | Scale |
|----|-------|-------|
| `learning_rate` | [1e-5, 5e-4] | log |
| `warmup_ratio` | [0.0, 0.1] | linear |
| `weight_decay` | [0.0, 0.1] | linear |
| `batch_size` | [8, 64] | log |
| `num_epochs` | [1, 10] | linear |
| `lora_r` (if LoRA) | [4, 64] | log |
| `lora_alpha` (if LoRA) | [8, 128] | log |

> **Tip**: For fine-tuning, learning rate is the highest-leverage HP. Tune it first with 5–10 trials before expanding the search.

### SVM / Kernel Methods

| HP | Range | Scale |
|----|-------|-------|
| `C` | [1e-2, 1e3] | log |
| `gamma` | [1e-4, 1e0] | log |
| `kernel` | `rbf`, `poly`, `linear` | categorical |

> **Warning**: SVM does not scale past ~100K samples without approximation (Nyström, SGD). Flag this.

---

## Successive Halving Quick Guide

Successive halving allocates budget proportionally, eliminating weak candidates early.

```
bracket = [C1, C2, C3, C4, C5]
round 1: all 5 candidates × 20 trials each → keep top 3
round 2: top 3 × 60 trials each → keep top 1
round 3: winner × 200 trials
```

Use `sklearn.model_selection.HalvingRandomSearchCV` or Optuna's `HyperbandPruner`.

---

## Early Stopping Rules

| Model type | Rule |
|------------|------|
| GBM | No improvement in primary metric for 50 rounds |
| Neural network | Validation loss plateau for 5 epochs |
| Bayesian search | Stop if best trial has not improved in last 20 trials |
| Wall-clock | Hard stop at 80% of per-candidate time-box |
