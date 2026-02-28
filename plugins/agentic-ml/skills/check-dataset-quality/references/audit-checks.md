# Dataset Audit Checks

Reference for the `dataset-audit` skill. Detailed check specifications with thresholds, severity criteria, and remediation guidance.

---

## Structural Checks

### Schema Consistency

**What**: Column names and dtypes must match across train/validation/test splits.

**Thresholds**:

- Any column name missing in one split → **blocker**
- Dtype mismatch on the same column across splits → **high** (will break inference pipeline)
- Extra columns in test not in train → **medium** (informational, may indicate leakage)

**Check**:

```python
train_cols = set(train_df.columns)
for split_name, split_df in {"validation": val_df, "test": test_df}.items():
    missing = train_cols - set(split_df.columns)
    extra = set(split_df.columns) - train_cols
    if missing:
        raise ValueError(f"Blocker: {split_name} missing columns: {missing}")
```

**Remediation**: Re-export splits from the same pipeline. Verify the feature engineering script is applied consistently.

---

### Parse Errors

**What**: Rows that fail to load, truncated JSONL lines, corrupt Parquet row groups.

**Thresholds**:

- Any parse error → **high** (silent data loss)
- > 1% parse failure rate → **blocker**

**Check (JSONL)**:

```python
errors = []
with open(path) as f:
    for i, line in enumerate(f):
        try:
            json.loads(line)
        except json.JSONDecodeError as e:
            errors.append((i, str(e)))
```

**Remediation**: Remove or quarantine corrupt rows. Log bad line numbers for source investigation.

---

## Missingness

### High Null Rate

**Thresholds**:

- Missing label column → **blocker**
- > 50% nulls in any feature column → **high**
- > 20% nulls in a feature column → **medium**
- > 5pp delta in null rate between train and test for the same column → **high** (distribution shift)

**Check**:

```python
null_rates = df.isnull().mean()
for col, rate in null_rates.items():
    if rate > 0.5:
        print(f"HIGH: {col} has {rate:.1%} nulls")
```

**Remediation**:

- Add null-indicator column before imputation to preserve missingness signal
- Investigate why split-specific nulls differ (collection artifact vs. feature availability)

---

## Duplicates

### Exact Row Duplicates

**Thresholds**:
>
- > 5% exact duplicates in training → **high** (inflated effective dataset size, biased evaluation)
- > 0.1% exact duplicates between train and test → **blocker** (leakage)

**Check**:

```python
dup_rate = df.duplicated().mean()
cross_dup = len(pd.merge(train_df, test_df, on=list(train_df.columns)))
```

**Remediation**: `df.drop_duplicates()`. For cross-split duplicates, rebuild splits with deduplication before splitting.

---

### Entity (ID) Leakage

**Thresholds**:

- Any `--id-col` overlap between train and test → **blocker**
- Any `--id-col` overlap between train and validation → **high**

**Check**:

```python
train_ids = set(train_df[id_col])
test_ids = set(test_df[id_col])
overlap = train_ids & test_ids
if overlap:
    print(f"BLOCKER: {len(overlap)} IDs appear in both train and test")
```

**Remediation**: Use group-based splitting (`GroupShuffleSplit` or `GroupKFold`) partitioned on `--id-col`.

---

## Label Health

### Class Imbalance (Classification)

**Thresholds**:

- Minority class < 0.5% → **high** (metric masking)
- Imbalance ratio > 100:1 → **high**
- Label present in train but absent in validation/test → **medium**

**Check**:

```python
counts = df[label_col].value_counts(normalize=True)
rare = counts[counts < 0.005]
if len(rare):
    print(f"HIGH: Rare classes: {rare.to_dict()}")
```

**Remediation**:

- Use `class_weight="balanced"` or `compute_class_weight`
- Switch primary metric to macro F1, PR-AUC, or MCC
- Consider oversampling minority class (SMOTE for tabular; augmentation for image/text)

---

### Target Distribution Sanity (Regression)

**Thresholds**:

- Any NaN/Inf in target → **blocker**
- Extreme skewness (|skew| > 10) → **high**
- Zero-inflated target with > 30% zeros → **medium** (consider log1p transform or two-stage model)

**Check**:

```python
from scipy.stats import skew
target_skew = skew(df[label_col].dropna())
zero_rate = (df[label_col] == 0).mean()
```

---

### Sequence Length Distribution (NLP)

**Thresholds**:
>
- > 10% of examples exceed model's `max_position_embeddings` → **high** (truncation loss)
- > 5% of examples are < 5 tokens → **medium** (degenerate inputs)

**Check**:

```python
# Using whitespace tokenizer as proxy; use actual tokenizer for accuracy
lengths = df[text_col].str.split().str.len()
print(f"p50={lengths.quantile(0.5)}, p95={lengths.quantile(0.95)}, p99={lengths.quantile(0.99)}")
```

**Remediation**: Use sliding window / strided tokenization to preserve long-document content.

---

## Outliers and Value Sanity

### Numeric Outliers

**Thresholds**:
>
- > 5% of values outside 5× IQR → **medium**
- Values that are physically impossible (negative age, latitude > 90) → **high**

**Check**:

```python
Q1, Q3 = df[col].quantile([0.25, 0.75])
IQR = Q3 - Q1
outlier_rate = ((df[col] < Q1 - 5*IQR) | (df[col] > Q3 + 5*IQR)).mean()
```

**Remediation**: Investigate data collection. Cap/clip or log-transform. Never silently drop outliers without logging.

---

### Text Outliers

**Thresholds**:
>
- > 1% of texts have length < 5 characters → **medium**
- > 0.5% of texts have length > 10× median length → **medium**
- Any texts that are exact duplicates of the label → **blocker** (leakage)

---

### Image Quality (Image Directories)

**Thresholds**:

- Any unreadable file → **high**
- > 1% corrupt files → **blocker**
- Aspect ratio outside [0.1, 10] → **medium** (may indicate wrong file)
- File size < 1KB → **medium** (likely placeholder or corrupt)

**Check**:

```python
from PIL import Image
import os

errors = []
for path in image_paths:
    try:
        img = Image.open(path)
        img.verify()
    except Exception as e:
        errors.append((path, str(e)))
```

---

## Leakage Checks

### Direct Feature Leakage

**What**: The label value appears verbatim or near-verbatim in a text or categorical feature.

**Thresholds**:

- Label string present in text feature in > 5% of rows → **blocker**
- Label-correlated feature with > 0.99 mutual information → **blocker**

**Check (text)**:

```python
label_in_text = df.apply(
    lambda row: str(row[label_col]).lower() in str(row[text_col]).lower(),
    axis=1
)
rate = label_in_text.mean()
if rate > 0.05:
    print(f"BLOCKER: label appears in text field in {rate:.1%} of rows")
```

---

### Temporal Leakage

**What**: Training examples are newer than validation/test examples (future data leaks into past).

**Check**:

```python
train_max_time = train_df[time_col].max()
val_min_time = val_df[time_col].min()
if train_max_time > val_min_time:
    overlap_rows = (train_df[time_col] > val_min_time).sum()
    print(f"BLOCKER: {overlap_rows} training rows are newer than validation start")
```

**Remediation**: Use time-based split with a buffer gap between train cutoff and validation start.
