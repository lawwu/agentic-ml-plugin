# Dataset Catalog

Use this catalog to pick repeatable benchmark datasets for E2E runs.

## adult-census-income

Prediction task:

- Predict whether annual income exceeds `$50K/yr` from census attributes.
- Also known as the **Adult** or **Census Income** dataset.

Suggested benchmark configuration:

- Task type: binary classification
- Primary metrics: `f1`, `roc_auc`, `auprc`
- Typical label column: income threshold target from dataset targets
- Good fit for: `clean-kaggle` scenario baseline

Fetch with `ucimlrepo`:

```bash
uv pip install ucimlrepo
```

```python
from ucimlrepo import fetch_ucirepo

# fetch dataset
adult = fetch_ucirepo(id=2)

# data (as pandas dataframes)
X = adult.data.features
y = adult.data.targets

# metadata
print(adult.metadata)

# variable information
print(adult.variables)
```

Benchmark notes:

- Validate categorical handling and missing-value treatment explicitly.
- Use a stable split and fixed seed for cross-harness comparability.
