# Tabular Pipeline Checks

Checks for scikit-learn, LightGBM, XGBoost, CatBoost, and pandas preprocessing. Most tabular leakage happens here: a transform that "sees" validation or test rows makes offline metrics look better than production will be.

Severity follows [vocabulary.md](../../../references/vocabulary.md).

## 1. Preprocessing fit on train only — `blocker` if violated

**What:** imputers, scalers, encoders, PCA, and feature selectors learn statistics. If they are fit on all rows before the split, validation and test statistics leak into training.

**Look for:** `.fit(` or `.fit_transform(` on a frame that has not been filtered to `train`; `df[col].fillna(df[col].mean())` on the full data; `pd.get_dummies` on the full data (also leaks the set of categories).

**Safe pattern:**

```python
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

pre = ColumnTransformer([
    ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num_cols),
    ("cat", make_pipeline(SimpleImputer(strategy="constant", fill_value="__missing__"),
                          OneHotEncoder(handle_unknown="ignore", min_frequency=20)), cat_cols),
])
pipe = Pipeline([("pre", pre), ("model", model)])
pipe.fit(X_train, y_train)          # statistics come from train only
```

**Check:** fit the pipeline on `train`, then confirm a fitted statistic matches `train`, not the full data:

```python
imp = pipe.named_steps["pre"].named_transformers_["num"].named_steps["simpleimputer"]
assert np.allclose(imp.statistics_, X_train[num_cols].median().values, equal_nan=True)
```

## 2. Target encoding is out-of-fold — `blocker` if violated

**What:** encoding a category by the mean label computed on rows that include the row being scored leaks that row's label.

**Safe:** sklearn `TargetEncoder` (it cross-fits inside `fit_transform`), or manual K-fold encoding on `train` with the encoder for `val`/`test` fit on all of `train`.

**Check:** on `train`, the encoded value for a row must not change when only that row's label is flipped. Equivalently, look for `groupby(cat)[label].mean()` merged back onto the same rows.

## 3. Resampling inside training folds — `blocker` if violated

**What:** SMOTE or over/under-sampling before the split puts synthetic copies of validation rows into training.

**Safe:** `imblearn.pipeline.Pipeline` with the sampler as a step, so it only runs during `fit`; or class weights (`class_weight="balanced"`, `scale_pos_weight`) instead of resampling.

**Check:** the validation and test row counts and label rates equal those in `split-manifest.json`.

## 4. Unseen categories — `high` if unhandled

**What:** a category that never appears in `train` arrives at inference and crashes the encoder, or is silently mis-encoded.

**Safe:** `OneHotEncoder(handle_unknown="ignore")`, `OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)`, LightGBM/CatBoost native categorical handling with a fixed category list, or an explicit `__other__` bucket.

**Check:** score a `val` copy with one categorical value replaced by `"__never_seen__"`; it must not raise, and the prediction must be finite.

## 5. Training/serving column contract — `high` if mismatched

**What:** the inference path builds features in a different order, with different dtypes, or with extra or missing columns.

**Check:**

- the fitted pipeline's `feature_names_in_` equals the inference frame's columns, in order
- dtype kinds match `data-contract.json`
- id, timestamp, and label columns are not features unless intended — record any that are
- the same function builds features for training and inference (no copy-pasted logic in a serving script)

## 6. Missing values handled identically — `medium`

**What:** training drops rows with nulls while serving imputes them (or vice versa), so the model never saw the inputs it now gets.

**Check:** count rows dropped by `dropna()` in the training path. If more than a small fraction, the serving path must make the same choice, or the model must handle nulls.

## 7. Splits come from the manifest — `blocker` if violated

**What:** the pipeline re-splits the data itself (e.g. `train_test_split` with a different seed or strategy), so the "validation" rows differ from the ones every other gate used, and test rows may leak in.

**Check:** the rows the pipeline trains on are exactly the `train` keys in `<out-dir>/splits/split_assignments.csv`. No `test` keys appear anywhere before the final evaluation.
