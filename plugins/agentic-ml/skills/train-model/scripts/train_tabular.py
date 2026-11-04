#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "joblib>=1.3",
#   "numpy>=1.24",
#   "pandas>=2.2",
#   "scikit-learn>=1.6",
# ]
# ///
"""
train_tabular.py: leakage-safe baseline trainer for tabular data (train-model skill).

  train    Fit a sklearn Pipeline on the train split, early-stop on val, optionally
           cross-validate on train+val, and write the model, metrics, and val predictions.
  predict  Score exactly one split (val or test) with a saved model.

Examples:
  uv run train_tabular.py train --data data.csv --splits out/splits --label-col churned \\
      --task binary --model hgb --cv-folds 5 --out-dir out/train
  uv run --with lightgbm train_tabular.py train ... --model lightgbm
  uv run train_tabular.py predict --model out/train/model.joblib --data data.csv \\
      --splits out/splits --split test --label-col churned --out out/train/predictions/model_test.csv

Leakage rules enforced here:
  * test/excluded rows are dropped right after loading and never reach fit().
  * every preprocessing statistic (medians, scales, category levels) is learned from train rows only.
  * CV folds follow the split strategy: groups never straddle folds, time folds only train on the past.
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import math
import platform
import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score, average_precision_score, brier_score_loss, f1_score, log_loss,
    mean_absolute_error, mean_squared_error, r2_score, roc_auc_score,
)
from sklearn.model_selection import GroupKFold, KFold, StratifiedKFold, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, OrdinalEncoder, StandardScaler

ROW_INDEX = "__row_index__"
SPLITS = {"train", "val", "test", "excluded"}
PRIMARY_METRIC = {"binary": "auprc", "multiclass": "f1_macro", "regression": "rmse"}
LGBM_PATIENCE = 50


def die(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


def import_lightgbm():
    try:
        import lightgbm
    except ImportError:
        die("lightgbm is not installed. Re-run with: uv run --with lightgbm train_tabular.py ...")
    return lightgbm


def clean(o):
    """Make an object JSON-safe: numpy scalars -> Python, NaN/inf -> null."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple, np.ndarray)):
        return [clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return round(float(o), 6) if math.isfinite(o) else None
    if o is None or isinstance(o, str):
        return o
    return str(o)


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(clean(obj), indent=2) + "\n")


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ loading

def read_splits(splits: str) -> tuple[dict, pd.Series]:
    d = Path(splits)
    d = d.parent if d.is_file() else d
    try:
        manifest = json.loads((d / "split-manifest.json").read_text())
        # keep_default_na=False so a key like "NA" stays a string, not NaN.
        assign = pd.read_csv(d / "split_assignments.csv", dtype=str, keep_default_na=False)
    except (OSError, ValueError) as e:
        die(f"cannot read splits from {d}: {e}")
    if not {"row_key", "split"} <= set(assign.columns):
        die("split_assignments.csv must have columns row_key,split")
    if assign["row_key"].duplicated().any():
        die("split_assignments.csv has duplicate row_key values")
    if bad := set(assign["split"]) - SPLITS:
        die(f"unknown split values {sorted(bad)}; expected {sorted(SPLITS)}")
    return manifest, assign.set_index("row_key")["split"]


def read_data(path: str, key_col: str | None) -> pd.DataFrame:
    # Read the key column as text so "007" and 7 never get confused when joining splits.
    dtype = {key_col: str} if key_col and key_col != ROW_INDEX else None
    try:
        df = pd.read_csv(path, dtype=dtype)
    except (OSError, ValueError) as e:
        die(f"cannot read data {path}: {e}")
    if key_col and key_col != ROW_INDEX and key_col not in df.columns:
        die(f"row_key column {key_col!r} not found in {path}")
    return df


def row_keys(df: pd.DataFrame, key_col: str) -> pd.Series:
    if key_col == ROW_INDEX:
        keys = pd.Series(np.arange(len(df)).astype(str), index=df.index)
    else:
        keys = df[key_col].astype(str)
    if keys.duplicated().any():
        die(f"row keys from {key_col!r} are not unique; splits cannot be joined safely")
    return keys


def load_split_rows(data: str, splits: str, keep: set[str]):
    """Load the data and keep only rows whose assigned split is in `keep`."""
    manifest, assign = read_splits(splits)
    key_col = manifest.get("row_key") or ROW_INDEX
    df = read_data(data, key_col)
    keys = row_keys(df, key_col)
    split = keys.map(assign)  # NaN where a row has no assignment
    n_unassigned = int(split.isna().sum())
    mask = split.isin(keep).to_numpy()
    # Held-out rows are dropped here, before any statistic is computed, so nothing
    # downstream (imputers, encoders, early stopping, CV) can ever see them.
    df = df.loc[mask].reset_index(drop=True)
    keys = keys[mask].reset_index(drop=True)
    split = split[mask].reset_index(drop=True)
    if not keep & {"test", "excluded"}:
        assert not split.isin(["test", "excluded"]).any(), "held-out rows reached training code"
    return df, keys, split, manifest, n_unassigned


# ------------------------------------------------------------------ features

def is_boolish(s: pd.Series) -> bool:
    """bool dtype, or an object column of True/False with NaN (how pandas reads a nullable bool CSV column)."""
    if pd.api.types.is_bool_dtype(s):
        return True
    if pd.api.types.is_object_dtype(s):
        nonnull = s.dropna()
        return len(nonnull) > 0 and all(isinstance(v, (bool, np.bool_)) for v in nonnull)
    return False


def select_features(df, label, manifest, drop_cols):
    """Split columns into numeric/categorical features; record why the rest are excluded."""
    excluded = {}
    for col, why in [(label, "label"), (manifest.get("row_key"), "row_key"),
                     (manifest.get("group_col"), "group_col"), (manifest.get("time_col"), "time_col")]:
        if col and col in df.columns:
            excluded.setdefault(col, why)
    notes = []
    for col in drop_cols:
        if col in df.columns:
            excluded.setdefault(col, "--drop-cols")
        else:
            notes.append(f"--drop-cols: {col!r} not in data")
    numeric, categorical = [], []
    for col in df.columns:
        if col in excluded:
            continue
        s = df[col]
        if pd.api.types.is_datetime64_any_dtype(s):
            excluded[col] = "datetime (derive features explicitly)"
        elif is_boolish(s) or pd.api.types.is_numeric_dtype(s):
            numeric.append(col)  # bools become 0/1
        else:
            categorical.append(col)
            nonnull = s.dropna()
            if len(nonnull) > 50 and nonnull.nunique() > 0.9 * len(nonnull):
                notes.append(f"{col!r} is ~unique per row (identifier or free text?); consider --drop-cols")
    return numeric, categorical, excluded, notes


def make_preprocessor(model: str, numeric, categorical, min_frequency: int) -> ColumnTransformer:
    # Medians come from train only. add_indicator keeps "was missing" as a feature (missingness is often
    # informative); keep_empty_features keeps an all-NaN column so output width is stable at serving time.
    num_steps = [("impute", SimpleImputer(strategy="median", add_indicator=True, keep_empty_features=True))]
    if model == "logreg":
        num_steps.append(("scale", StandardScaler()))  # linear models need comparable scales; trees don't
    impute_cat = ("impute", SimpleImputer(strategy="constant", fill_value="__missing__"))
    if model == "hgb":
        # Integer codes for HGB's native categorical splits. Unknown levels at serving -> NaN (missing branch).
        encode = OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=np.nan,
                                min_frequency=min_frequency, max_categories=250)
    else:
        # Rare levels are pooled (min_frequency) so they can't be memorised; unseen levels -> all zeros.
        encode = OneHotEncoder(handle_unknown="ignore", min_frequency=min_frequency, sparse_output=False)
    # Categorical block first: its width is fixed, so HGB can address it by column index.
    return ColumnTransformer(
        [("cat", Pipeline([impute_cat, ("encode", encode)]), list(categorical)),
         ("num", Pipeline(num_steps), list(numeric))],
        remainder="drop", sparse_threshold=0,
    )


def make_estimator(model, task, n_cat, seed, class_weight, n_estimators=None):
    clf = task != "regression"
    if model == "logreg":
        if not clf:
            return Ridge(alpha=1.0)  # linear baseline for regression
        return LogisticRegression(max_iter=2000, class_weight=class_weight, random_state=seed)
    if model == "hgb":
        cls = HistGradientBoostingClassifier if clf else HistGradientBoostingRegressor
        kw = {"class_weight": class_weight} if clf else {}
        # The preprocessor emits the n_cat ordinal-encoded columns first.
        cat_idx = list(range(n_cat)) or None
        # early_stopping holds out validation_fraction of *train* internally (a random row split).
        return cls(max_iter=500, learning_rate=0.05, early_stopping=True, validation_fraction=0.1,
                   n_iter_no_change=20, categorical_features=cat_idx, random_state=seed, **kw)
    lgb = import_lightgbm()
    cls = lgb.LGBMClassifier if clf else lgb.LGBMRegressor
    kw = {"class_weight": class_weight} if clf else {}
    return cls(n_estimators=n_estimators or 2000, learning_rate=0.05, num_leaves=31, random_state=seed,
               deterministic=True, force_col_wise=True, verbose=-1, **kw)


def build_pipeline(args, task, numeric, categorical, n_estimators=None) -> Pipeline:
    return Pipeline([
        ("prep", make_preprocessor(args.model, numeric, categorical, args.min_frequency)),
        ("model", make_estimator(args.model, task, len(categorical), args.seed,
                                 args.class_weight, n_estimators)),
    ])


def fit_pipeline(args, pipe: Pipeline, X_tr, y_tr, X_va=None, y_va=None) -> Pipeline:
    if args.model != "lightgbm" or X_va is None or len(X_va) == 0:
        return pipe.fit(X_tr, y_tr)
    lgb = import_lightgbm()
    prep, est = pipe.named_steps["prep"], pipe.named_steps["model"]
    # Early stopping must see val exactly as serving will: transformed by the preprocessor
    # fit on TRAIN. Passing raw val (or refitting prep on val) is a classic silent bug.
    Z_tr = prep.fit_transform(X_tr, y_tr)
    Z_va = prep.transform(X_va)
    # Prefer eval_set while it exists: LightGBM 4.7 deprecates it for eval_X/eval_y, but its classifier
    # only label-encodes eval_set, so eval_y breaks on string labels.
    if "eval_set" in inspect.signature(est.fit).parameters:
        eval_kw = {"eval_set": [(Z_va, y_va)]}
    else:
        eval_kw = {"eval_X": (Z_va,), "eval_y": (y_va,)}
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*eval_set.*deprecated")
        est.fit(Z_tr, y_tr, callbacks=[lgb.early_stopping(LGBM_PATIENCE, verbose=False)], **eval_kw)
    return pipe  # both steps are now fitted in place


# ------------------------------------------------------------------ predictions & metrics

def predict_frame(pipe, X, keys, y_true, meta) -> pd.DataFrame:
    """Predictions in the shared row_key,y_true,... format."""
    task = meta["task"]
    out = pd.DataFrame({"row_key": np.asarray(keys), "y_true": np.asarray(y_true)})
    if task == "regression":
        out["y_pred"] = pipe.predict(X)
        return out
    proba = pipe.predict_proba(X)
    classes = pipe.classes_
    if task == "binary":
        pos = int(np.flatnonzero(classes == meta["pos_label"])[0])
        out["y_score"] = proba[:, pos]
        out["y_pred"] = classes[np.where(proba[:, pos] >= 0.5, pos, 1 - pos)]
    else:
        for j, c in enumerate(classes):
            out[f"score_{c}"] = proba[:, j]
        out["y_pred"] = classes[proba.argmax(axis=1)]
    return out


def score_metrics(task, y_true, pred: pd.DataFrame, classes, pos_label) -> dict:
    y_true = np.asarray(y_true)
    m: dict = {"n": len(y_true)}
    if len(y_true) == 0:
        return m
    y_pred = pred["y_pred"].to_numpy()
    if task == "regression":
        m["rmse"] = math.sqrt(mean_squared_error(y_true, y_pred))
        m["mae"] = mean_absolute_error(y_true, y_pred)
        m["r2"] = r2_score(y_true, y_pred) if len(y_true) > 1 else None
        return m
    m["accuracy"] = accuracy_score(y_true, y_pred)
    if task == "binary":
        yb = (y_true == pos_label).astype(int)
        s = pred["y_score"].to_numpy()
        both = 0 < yb.sum() < len(yb)  # ranking metrics need both classes present
        m["prevalence"] = yb.mean()
        m["auprc"] = average_precision_score(yb, s) if both else None
        m["roc_auc"] = roc_auc_score(yb, s) if both else None
        m["log_loss"] = log_loss(yb, np.clip(s, 1e-15, 1 - 1e-15), labels=[0, 1])
        m["brier"] = brier_score_loss(yb, s)
        m["f1_at_0.5"] = f1_score(yb, (y_pred == pos_label).astype(int), zero_division=0)
    else:
        proba = pred[[f"score_{c}" for c in classes]].to_numpy()
        m["f1_macro"] = f1_score(y_true, y_pred, average="macro", zero_division=0)
        unseen = set(y_true.tolist()) - set(classes)  # a class missing from train can't get a probability
        m["log_loss"] = None if unseen else log_loss(y_true, np.clip(proba, 1e-15, 1), labels=classes)
    return m


# ------------------------------------------------------------------ cross-validation

def cv_folds(manifest, df, y, task, k, seed):
    """Folds that mirror how train/val/test were split, so CV estimates the same generalisation."""
    strategy = manifest.get("strategy", "random")
    n = len(df)
    if strategy == "group":
        g = manifest.get("group_col")
        if not g or g not in df.columns:
            die(f"group strategy but group_col {g!r} is not in the data")
        # One group (e.g. one customer) is never in both the fit and the score fold.
        return "GroupKFold", list(GroupKFold(n_splits=k).split(np.zeros(n), y, df[g].astype(str)))
    if strategy == "time":
        t = manifest.get("time_col")
        if not t or t not in df.columns:
            die(f"time strategy but time_col {t!r} is not in the data")
        times = df[t] if pd.api.types.is_numeric_dtype(df[t]) else pd.to_datetime(df[t], errors="coerce", format="ISO8601")
        uniq = np.sort(times.dropna().unique())
        if len(uniq) < k + 1:
            die(f"time CV needs more than {k} distinct {t!r} values; got {len(uniq)}")
        folds = []
        # Split unique timestamps, not rows: rows sharing a timestamp stay together and
        # every fold trains on the past and scores on the future (expanding window).
        for tr, te in TimeSeriesSplit(n_splits=k).split(uniq):
            folds.append((np.flatnonzero(times.isin(uniq[tr]).to_numpy()),
                          np.flatnonzero(times.isin(uniq[te]).to_numpy())))
        return "TimeSeriesSplit(unique time values, expanding)", folds
    if task == "regression":
        return "KFold", list(KFold(k, shuffle=True, random_state=seed).split(np.zeros(n)))
    return "StratifiedKFold", list(StratifiedKFold(k, shuffle=True, random_state=seed).split(np.zeros(n), y))


def run_cv(args, df, y, numeric, categorical, manifest, task, meta, best_iteration):
    primary = PRIMARY_METRIC[task]
    fold_type, folds = cv_folds(manifest, df, y, task, args.cv_folds, args.seed)
    X = df[numeric + categorical]
    rows = []
    for i, (tr, te) in enumerate(folds):
        # A fresh, unfitted pipeline per fold: imputers/encoders learn from this fold's train rows only.
        # LightGBM uses the val-selected tree count instead of early-stopping on the fold it is scored on.
        pipe = build_pipeline(args, task, numeric, categorical, n_estimators=best_iteration)
        pipe.fit(X.iloc[tr], y[tr])
        pred = predict_frame(pipe, X.iloc[te], np.arange(len(te)), y[te], meta)
        m = score_metrics(task, y[te], pred, pipe.classes_ if task != "regression" else None, meta.get("pos_label"))
        rows.append({"fold": i, "n_fit": len(tr), "n_score": len(te), primary: m.get(primary)})
    vals = [r[primary] for r in rows if r[primary] is not None]
    return {
        "fold_type": fold_type, "k": len(folds), "on": "train+val", "metric": primary, "folds": rows,
        "mean": float(np.mean(vals)) if vals else None,
        "std": float(np.std(vals, ddof=1)) if len(vals) > 1 else None,
        "note": "lightgbm CV uses n_estimators fixed at the val best_iteration" if args.model == "lightgbm" else None,
    }


# ------------------------------------------------------------------ commands

def resolve_pos_label(classes, requested):
    if requested is not None:
        for c in classes:
            if str(c) == requested:
                return c
        die(f"--pos-label {requested!r} is not one of the classes {[str(c) for c in classes]}")
    return classes[-1]  # True for bool labels, 1 for 0/1 labels, last in sorted order otherwise


def cmd_train(args) -> None:
    out_dir = Path(args.out_dir)
    keep = {"train", "val"}
    df, keys, split, manifest, n_unassigned = load_split_rows(args.data, args.splits, keep)
    if args.label_col not in df.columns:
        die(f"label column {args.label_col!r} not in data")
    notes = [f"{n_unassigned} data rows have no split assignment and were ignored"] if n_unassigned else []

    # Rows without a label cannot be fit or scored.
    labelled = df[args.label_col].notna().to_numpy()
    if not labelled.all():
        notes.append(f"dropped {int((~labelled).sum())} train/val rows with a missing label")
        df = df[labelled].reset_index(drop=True)
        keys = keys[labelled].reset_index(drop=True)
        split = split[labelled].reset_index(drop=True)
    y_all = df[args.label_col]
    if args.task == "regression":
        y_all = pd.to_numeric(y_all, errors="coerce")
        if y_all.isna().any():
            die(f"regression label {args.label_col!r} has non-numeric values")
    else:
        y_all = y_all.infer_objects()  # object True/False (from a column that had blanks) -> bool
    y_all = y_all.to_numpy()
    is_tr, is_va = (split == "train").to_numpy(), (split == "val").to_numpy()
    if not is_tr.any():
        die("no labelled train rows")
    if not is_va.any():
        notes.append("no val rows: val metrics and early stopping on val are skipped (lightgbm uses 200 trees)")

    numeric, categorical, excluded, feat_notes = select_features(df, args.label_col, manifest, args.drop_cols)
    notes += feat_notes
    if not numeric + categorical:
        die("no feature columns left after exclusions")
    X = df[numeric + categorical]

    meta = {"task": args.task, "label_col": args.label_col, "row_key": manifest.get("row_key") or ROW_INDEX,
            "numeric_features": numeric, "categorical_features": categorical, "model": args.model,
            "test_keys_sha256": manifest.get("test_keys_sha256")}
    if args.task != "regression":
        classes = np.unique(y_all[is_tr])
        if args.task == "binary" and len(classes) != 2:
            die(f"binary task needs exactly 2 classes in train, found {len(classes)}: {classes[:10].tolist()}")
        meta["pos_label"] = resolve_pos_label(classes, args.pos_label) if args.task == "binary" else None
        meta["classes"] = classes.tolist()

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        pipe = build_pipeline(args, args.task, numeric, categorical, n_estimators=None if is_va.any() else 200)
        pipe = fit_pipeline(args, pipe, X[is_tr], y_all[is_tr], X[is_va], y_all[is_va])
    notes += sorted({f"{w.category.__name__}: {str(w.message)[:160]}" for w in caught})[:5]
    # Stash what serving needs on the pipeline itself so model.joblib is self-describing.
    pipe.agentic_ml_ = meta

    est = pipe.named_steps["model"]
    if args.model == "lightgbm":
        best_iteration = getattr(est, "best_iteration_", None) or est.n_estimators
        early = {"type": "lightgbm early_stopping callback", "monitor": "default loss on val split",
                 "patience": LGBM_PATIENCE, "used": bool(is_va.any())}
    elif args.model == "hgb":
        best_iteration = int(est.n_iter_)
        early = {"type": "HistGradientBoosting internal", "validation_fraction": 0.1,
                 "n_iter_no_change": 20, "source": "random 10% of TRAIN rows (val split untouched)",
                 "best_iteration_means": "n_iter_ (iterations kept; HGB does not roll back to the best one)"}
        if manifest.get("strategy") in ("group", "time"):
            notes.append("hgb internal early-stopping holdout is a random row split, not group/time-aware")
    else:
        best_iteration, early = None, {"type": "none"}

    val_pred, val_metrics = None, None
    if is_va.any():
        val_pred = predict_frame(pipe, X[is_va], keys[is_va], y_all[is_va], meta)
        val_metrics = score_metrics(args.task, y_all[is_va], val_pred, meta.get("classes"), meta.get("pos_label"))
        too_good = val_metrics.get("r2") if args.task == "regression" else val_metrics.get(PRIMARY_METRIC[args.task])
        if too_good is not None and too_good >= 0.99:
            notes.append("near-perfect val score: check features for target leakage before trusting it")

    cv = None
    if args.cv_folds:
        if args.cv_folds < 2:
            die("--cv-folds must be >= 2")
        cv = run_cv(args, df, y_all, numeric, categorical, manifest, args.task, meta,
                    best_iteration if args.model == "lightgbm" else None)

    # ---- write artifacts
    (out_dir / "predictions").mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, out_dir / "model.joblib")
    if val_pred is not None:
        val_pred.to_csv(out_dir / "predictions" / "model_val.csv", index=False)
    primary = PRIMARY_METRIC[args.task]
    write_json(out_dir / "train-metrics.json", {
        "task": args.task, "model": args.model, "primary_metric": primary,
        "val": val_metrics, "cv": cv, "best_iteration": best_iteration, "early_stopping": early,
        "n_train": int(is_tr.sum()), "n_val": int(is_va.sum()), "notes": notes,
    })
    versions = {"python": platform.python_version(), "sklearn": sklearn.__version__,
                "pandas": pd.__version__, "numpy": np.__version__}
    if args.model == "lightgbm":
        versions["lightgbm"] = import_lightgbm().__version__
    write_json(out_dir / "train-config.json", {
        "args": vars(args) | {"func": None}, "seed": args.seed,
        "features": {"numeric": numeric, "categorical": categorical}, "excluded_columns": excluded,
        "label": {"col": args.label_col, "classes": meta.get("classes"), "pos_label": meta.get("pos_label")},
        "model_params": est.get_params(), "data_sha256": sha256_file(args.data),
        "split_manifest": {k: manifest.get(k) for k in ("strategy", "row_key", "group_col", "time_col", "seed")},
        "test_keys_sha256": manifest.get("test_keys_sha256"), "versions": versions,
    })

    # ---- stdout summary
    print(f"train_tabular: {args.model} {args.task} | n_train={int(is_tr.sum())} n_val={int(is_va.sum())} "
          f"| features: {len(numeric)} numeric, {len(categorical)} categorical")
    if val_metrics:
        shown = {k: v for k, v in val_metrics.items() if k in (primary, "roc_auc", "log_loss", "mae", "accuracy")}
        print("  val " + " ".join(f"{k}={v:.4f}" for k, v in shown.items() if v is not None)
              + (f" | best_iteration={best_iteration}" if best_iteration is not None else ""))
    if cv and cv["mean"] is not None:
        std = f" ± {cv['std']:.4f}" if cv["std"] is not None else ""
        print(f"  cv {cv['fold_type']} k={cv['k']}: {primary} {cv['mean']:.4f}{std}")
    for n in notes:
        print(f"  note: {n}")
    print(f"  wrote {out_dir}/model.joblib, train-metrics.json, train-config.json, predictions/model_val.csv")


def load_model(path: str):
    try:
        pipe = joblib.load(path)
    except ModuleNotFoundError as e:
        die(f"{e}. If the model is LightGBM, run with: uv run --with lightgbm ...")
    except (OSError, ValueError, EOFError) as e:
        die(f"cannot load model {path}: {e}")
    if not hasattr(pipe, "agentic_ml_"):
        die("model has no agentic_ml_ metadata; was it trained by train_tabular.py?")
    return pipe


def cmd_predict(args) -> None:
    pipe = load_model(args.model)
    meta = pipe.agentic_ml_
    df, keys, _, manifest, _ = load_split_rows(args.data, args.splits, {args.split})
    if df.empty:
        die(f"no rows assigned to split {args.split!r}")
    trained_hash, current_hash = meta.get("test_keys_sha256"), manifest.get("test_keys_sha256")
    if trained_hash and current_hash and trained_hash != current_hash:
        msg = "split manifest changed since training (test_keys_sha256 differs): the model may have trained on these rows"
        if args.split == "test":
            die(msg)
        print(f"warning: {msg}", file=sys.stderr)
    missing = [c for c in pipe.feature_names_in_ if c not in df.columns]
    if missing:
        die(f"data is missing feature columns the model was trained on: {missing}")
    label = args.label_col or meta["label_col"]
    y_true = df[label] if label in df.columns else pd.Series(np.nan, index=df.index)
    pred = predict_frame(pipe, df[list(pipe.feature_names_in_)], keys, y_true, meta)
    out = Path(args.out)
    if args.split == "test" and out.exists():
        print(f"warning: {out} already exists. Scoring test repeatedly turns it into a validation set.", file=sys.stderr)
    out.parent.mkdir(parents=True, exist_ok=True)
    pred.to_csv(out, index=False)
    print(f"train_tabular predict: {len(pred)} {args.split} rows -> {out}")
    if args.split == "test":
        print("  reminder: evaluate test predictions exactly once, after all model choices are frozen")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("train", help="fit on train, early-stop on val, optional CV on train+val")
    t.add_argument("--data", required=True, help="CSV with all rows (split membership comes from --splits)")
    t.add_argument("--splits", required=True, help="dir with split_assignments.csv and split-manifest.json")
    t.add_argument("--label-col", required=True)
    t.add_argument("--task", required=True, choices=["binary", "multiclass", "regression"])
    t.add_argument("--drop-cols", default="", type=lambda s: [c for c in s.split(",") if c],
                   help="comma-separated columns to exclude from features (e.g. leaky or ID columns)")
    t.add_argument("--model", default="hgb", choices=["logreg", "hgb", "lightgbm"],
                   help="logreg (Ridge for regression), hgb (sklearn HistGradientBoosting), lightgbm (needs --with lightgbm)")
    t.add_argument("--cv-folds", type=int, default=0, help="K-fold CV on train+val matching the split strategy (0 = off)")
    t.add_argument("--seed", type=int, default=42)
    t.add_argument("--class-weight", choices=["balanced"], default=None)
    t.add_argument("--pos-label", default=None, help="positive class for binary (default: True / 1 / last sorted class)")
    t.add_argument("--min-frequency", type=int, default=10, help="categories seen fewer times in train are pooled")
    t.add_argument("--out-dir", required=True)
    t.set_defaults(func=cmd_train)

    q = sub.add_parser("predict", help="score one split with a saved model")
    q.add_argument("--model", required=True, help="model.joblib written by `train`")
    q.add_argument("--data", required=True)
    q.add_argument("--splits", required=True)
    q.add_argument("--split", required=True, choices=["val", "test"])
    q.add_argument("--label-col", default=None, help="label column for y_true (default: the trained label)")
    q.add_argument("--out", required=True, help="output predictions CSV")
    q.set_defaults(func=cmd_predict)
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    a.func(a)
