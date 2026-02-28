#!/usr/bin/env python3
"""
feature_importance.py — Standardized feature importance computation for explain-model.

Supports SHAP (TreeExplainer, DeepExplainer, KernelExplainer),
permutation importance, and model built-in importance.

Usage:
    uv run scripts/feature_importance.py \
        --model <path> \
        --data <path> \
        --label-col <col> \
        --method auto|shap|permutation|builtin \
        --out-dir <dir>
"""

import argparse
import json
import os
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Compute feature importance for a trained model.")
    p.add_argument("--model", required=True, help="Path to model file (.pkl, .joblib, .json, .pt, or HF dir)")
    p.add_argument("--data", required=True, help="Path to validation dataset (.csv, .parquet, .jsonl)")
    p.add_argument("--label-col", required=True, help="Target column name")
    p.add_argument(
        "--method",
        default="auto",
        choices=["auto", "shap", "permutation", "builtin"],
        help="Importance method (default: auto)",
    )
    p.add_argument("--out-dir", default="./explain_output", help="Output directory")
    p.add_argument("--top-n", type=int, default=20, help="Number of top features to report")
    p.add_argument("--n-repeats", type=int, default=10, help="Repeats for permutation importance")
    p.add_argument("--shap-sample", type=int, default=500, help="Max rows for SHAP KernelExplainer background")
    p.add_argument("--scoring", default=None, help="Scoring metric for permutation importance (sklearn name)")
    return p.parse_args()


def load_data(data_path: str, label_col: str):
    """Load dataset and split into X, y."""
    import pandas as pd

    path = Path(data_path)
    if path.suffix == ".csv":
        df = pd.read_csv(path)
    elif path.suffix == ".parquet":
        df = pd.read_parquet(path)
    elif path.suffix in (".jsonl", ".ndjson"):
        df = pd.read_json(path, lines=True)
    else:
        raise ValueError(f"Unsupported data format: {path.suffix}. Use .csv, .parquet, or .jsonl.")

    if label_col not in df.columns:
        raise ValueError(f"Label column '{label_col}' not found. Available: {list(df.columns)}")

    y = df[label_col]
    X = df.drop(columns=[label_col])
    return X, y


def load_model(model_path: str):
    """Load a serialized model. Supports joblib, pickle, XGBoost JSON, and HF directories."""
    import importlib

    path = Path(model_path)

    if path.suffix in (".pkl", ".pickle"):
        import pickle
        with open(path, "rb") as f:
            return pickle.load(f)

    if path.suffix in (".joblib",):
        joblib = importlib.import_module("joblib")
        return joblib.load(path)

    if path.suffix == ".json":
        try:
            xgb = importlib.import_module("xgboost")
            model = xgb.XGBClassifier()
            model.load_model(str(path))
            return model
        except (ImportError, Exception):
            pass
        try:
            lgb = importlib.import_module("lightgbm")
            return lgb.Booster(model_file=str(path))
        except (ImportError, Exception):
            pass

    if path.is_dir():
        # HuggingFace checkpoint directory
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained(str(path))
            model = AutoModelForSequenceClassification.from_pretrained(str(path))
            return (model, tokenizer)
        except Exception as e:
            raise ValueError(f"Could not load HF model from {path}: {e}")

    raise ValueError(
        f"Cannot load model from '{path}'. Supported: .pkl, .pickle, .joblib, .json (XGBoost/LightGBM), "
        "or HuggingFace checkpoint directory."
    )


def detect_method(model, method: str) -> str:
    """Resolve 'auto' to a concrete method based on model type."""
    if method != "auto":
        return method

    model_type = type(model).__name__.lower()
    tree_types = {"xgbclassifier", "xgbregressor", "lgbmclassifier", "lgbmregressor",
                  "randomforestclassifier", "randomforestregressor", "gradientboostingclassifier",
                  "gradientboostingregressor", "decisiontreeclassifier", "decisiontreeregressor",
                  "catboostclassifier", "catboostregressor", "booster"}

    if any(t in model_type for t in tree_types):
        return "shap"

    linear_types = {"logisticregression", "linearregression", "ridge", "lasso", "elasticnet",
                    "sgdclassifier", "sgdregressor"}
    if any(t in model_type for t in linear_types):
        return "builtin"

    return "permutation"


def compute_shap(model, X, shap_sample: int) -> dict:
    """Compute SHAP values and return mean |SHAP| per feature."""
    try:
        import shap
        import numpy as np
    except ImportError:
        print("SHAP not installed. Run: uv pip install shap", file=sys.stderr)
        sys.exit(1)

    model_type = type(model).__name__.lower()
    tree_types = {"xgbclassifier", "xgbregressor", "lgbmclassifier", "lgbmregressor",
                  "randomforestclassifier", "randomforestregressor", "gradientboostingclassifier",
                  "gradientboostingregressor", "decisiontreeclassifier", "decisiontreeregressor",
                  "catboostclassifier", "catboostregressor", "booster"}

    if any(t in model_type for t in tree_types):
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X)
    else:
        # KernelExplainer — sample background for speed
        background = X.sample(min(shap_sample, len(X)), random_state=42)
        explainer = shap.KernelExplainer(model.predict, background)
        shap_values = explainer.shap_values(X.sample(min(shap_sample, len(X)), random_state=0))

    # Handle multi-class (list of arrays) → use class 1 or mean across classes
    if isinstance(shap_values, list):
        shap_array = np.abs(np.array(shap_values)).mean(axis=0)
    else:
        shap_array = np.abs(shap_values)

    mean_abs = shap_array.mean(axis=0)
    return dict(zip(X.columns, mean_abs.tolist()))


def compute_permutation(model, X, y, n_repeats: int, scoring) -> dict:
    """Compute permutation importance using sklearn."""
    from sklearn.inspection import permutation_importance

    result = permutation_importance(model, X, y, n_repeats=n_repeats, scoring=scoring, random_state=42)
    return dict(zip(X.columns, result.importances_mean.tolist()))


def compute_builtin(model, X) -> dict:
    """Extract built-in feature importance (coefficients or feature_importances_)."""
    import numpy as np

    if hasattr(model, "feature_importances_"):
        scores = model.feature_importances_
    elif hasattr(model, "coef_"):
        coef = model.coef_
        if coef.ndim > 1:
            scores = np.abs(coef).mean(axis=0)
        else:
            scores = np.abs(coef)
    elif hasattr(model, "feature_importance"):
        # LightGBM Booster
        scores = model.feature_importance(importance_type="gain")
        feature_names = model.feature_name()
        return dict(zip(feature_names, scores.tolist()))
    else:
        raise ValueError(
            f"Model type '{type(model).__name__}' does not expose built-in importance. "
            "Use --method permutation or shap."
        )

    return dict(zip(X.columns, scores.tolist()))


def rank_features(importance_dict: dict, top_n: int) -> list[dict]:
    """Sort features by importance and assign ranks."""
    sorted_items = sorted(importance_dict.items(), key=lambda x: x[1], reverse=True)
    return [
        {"rank": i + 1, "feature": name, "importance": round(score, 6)}
        for i, (name, score) in enumerate(sorted_items[:top_n])
    ]


def save_results(ranked: list[dict], method: str, out_dir: str) -> None:
    """Save importance results as JSON and print a text table."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    json_file = out_path / "feature_importance.json"
    with open(json_file, "w") as f:
        json.dump({"method": method, "features": ranked}, f, indent=2)

    # Print text table
    print(f"\nFeature Importance ({method}) — Top {len(ranked)}")
    print("-" * 50)
    print(f"{'Rank':>4}  {'Feature':<35}  {'Importance':>12}")
    print("-" * 50)
    for row in ranked:
        print(f"{row['rank']:>4}  {row['feature']:<35}  {row['importance']:>12.6f}")
    print("-" * 50)
    print(f"\nSaved to: {json_file}")


def main() -> None:
    args = parse_args()

    print(f"Loading data from: {args.data}")
    X, y = load_data(args.data, args.label_col)
    print(f"  Rows: {len(X):,}  |  Features: {len(X.columns)}")

    print(f"Loading model from: {args.model}")
    model = load_model(args.model)

    method = detect_method(model, args.method)
    print(f"Method: {method}")

    if method == "shap":
        importance = compute_shap(model, X, args.shap_sample)
    elif method == "permutation":
        importance = compute_permutation(model, X, y, args.n_repeats, args.scoring)
    elif method == "builtin":
        importance = compute_builtin(model, X)
    else:
        raise ValueError(f"Unknown method: {method}")

    ranked = rank_features(importance, args.top_n)
    save_results(ranked, method, args.out_dir)


if __name__ == "__main__":
    main()
