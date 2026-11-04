#!/usr/bin/env -S uv run --script
"""
profile-dataset.py — statistical profiling script for the check-dataset-quality skill.
Usage: uv run "${CLAUDE_SKILL_DIR}/scripts/profile-dataset.py" <path>
           [--format csv|parquet|jsonl] [--label-col COL] [--task auto|classification|regression]
           [--text-col COL] [--id-col COL] [--sample N] [--output OUTPUT.json]

Outputs a JSON stats object to --output (default: stdout).
"""
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "pandas>=2.0",
#   "pyarrow>=14",
# ]
# ///
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", help="Dataset path (file or directory)")
    p.add_argument("--format", choices=["csv", "parquet", "jsonl", "auto"], default="auto")
    p.add_argument("--label-col", default=None, help="Target/label column name")
    p.add_argument(
        "--task",
        choices=["auto", "classification", "regression"],
        default="auto",
        help="Label type for label_health (default: infer from the label column)",
    )
    p.add_argument("--text-col", default=None, help="Primary text column name")
    p.add_argument("--id-col", default=None, help="Unique entity identifier column")
    p.add_argument("--sample", type=int, default=None, help="Max rows to load")
    p.add_argument("--output", default=None, help="Output JSON path (default: stdout)")
    return p.parse_args()


def detect_format(path: str) -> str:
    p = Path(path)
    if p.is_dir():
        return "parquet"
    suffix = p.suffix.lower()
    return {".csv": "csv", ".parquet": "parquet", ".jsonl": "jsonl"}.get(suffix, "csv")


def load_dataframe(path: str, fmt: str, sample: int | None):
    """Load dataset into a pandas DataFrame with optional sampling."""
    import pandas as pd

    if fmt == "csv":
        df = pd.read_csv(path, nrows=sample)
    elif fmt == "parquet":
        p = Path(path)
        if p.is_dir():
            files = sorted(p.rglob("*.parquet"))
            if not files:
                raise ValueError(f"No .parquet files found under directory: {path}")
            df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        else:
            df = pd.read_parquet(path)
        if sample is not None:
            df = df.sample(n=min(sample, len(df)), random_state=42)
    elif fmt == "jsonl":
        import json as _json
        rows = []
        with open(path) as f:
            for i, line in enumerate(f):
                if sample is not None and i >= sample:
                    break
                line = line.strip()
                if line:
                    try:
                        rows.append(_json.loads(line))
                    except _json.JSONDecodeError:
                        pass
        df = pd.DataFrame(rows)
    else:
        raise ValueError(f"Unsupported format: {fmt}")
    return df


def _is_nested(v) -> bool:
    return isinstance(v, (list, dict, set, tuple))


def flatten_nested_columns(df) -> list[str]:
    """Serialize list/dict cell values (common in JSONL) to JSON strings in place.

    pandas cannot hash these values, so nunique()/duplicated() would crash.
    Returns the names of the columns that were converted.
    """
    nested = []
    for c in df.columns:
        if df[c].dtype != object:
            continue
        if df[c].map(_is_nested).any():
            df[c] = df[c].map(
                lambda v: json.dumps(v if not isinstance(v, set) else sorted(v, key=str),
                                     sort_keys=True, default=str)
                if _is_nested(v) else v
            )
            nested.append(str(c))
    return nested


def _is_text(series) -> bool:
    import pandas as pd

    # pandas >= 3 uses the "str" dtype by default; older pandas uses object.
    return series.dtype == object or pd.api.types.is_string_dtype(series.dtype)


def profile_column(series, col_name: str, nested: bool = False) -> dict:
    """Compute per-column stats."""
    import pandas as pd

    total = len(series)
    null_count = int(series.isnull().sum())
    stats: dict = {
        "name": col_name,
        "dtype": str(series.dtype),
        "count": int(series.count()),
        "null_count": null_count,
        "null_rate": _safe_rate(null_count, total),
        "unique_count": int(series.nunique()),
    }
    if nested:
        stats["nested"] = True

    if pd.api.types.is_bool_dtype(series.dtype):
        stats["true_rate"] = _safe_rate(int(series.fillna(False).astype(bool).sum()), int(series.count()))

    elif series.dtype.kind in ("i", "u", "f"):  # numeric
        desc = series.describe()
        stats.update({
            "min": _safe_float(desc.get("min")),
            "max": _safe_float(desc.get("max")),
            "mean": _safe_float(desc.get("mean")),
            "std": _safe_float(desc.get("std")),
            "p25": _safe_float(series.quantile(0.25)),
            "p50": _safe_float(series.quantile(0.50)),
            "p75": _safe_float(series.quantile(0.75)),
            "p95": _safe_float(series.quantile(0.95)),
            "p99": _safe_float(series.quantile(0.99)),
        })
        # Outlier rate (5× IQR)
        q1, q3 = series.quantile(0.25), series.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            outlier_mask = (series < q1 - 5 * iqr) | (series > q3 + 5 * iqr)
            stats["outlier_rate_5iqr"] = round(float(outlier_mask.mean()), 4)

    elif _is_text(series):  # text
        lengths = series.dropna().astype(str).str.len()
        stats.update({
            "min_len": int(lengths.min()) if len(lengths) > 0 else None,
            "max_len": int(lengths.max()) if len(lengths) > 0 else None,
            "mean_len": round(float(lengths.mean()), 1) if len(lengths) > 0 else None,
            "p95_len": round(float(lengths.quantile(0.95)), 1) if len(lengths) > 0 else None,
            "top_values": {str(k): int(v) for k, v in series.value_counts().head(5).items()}
            if 0 < stats["unique_count"] <= 100 else None,
        })

    return stats


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        return None if (f != f) else round(f, 6)  # NaN check
    except (TypeError, ValueError):
        return None


def _safe_rate(numerator: int | float, denominator: int | float) -> float | None:
    if not denominator:
        return None
    return round(float(numerator) / float(denominator), 4)


def _sanitize_for_json(obj):
    """Convert NaN/Inf recursively so output is valid strict JSON."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, tuple):
        return tuple(_sanitize_for_json(v) for v in obj)
    return obj


MAX_CLASSES_REPORTED = 50


def infer_label_task(series) -> str:
    """Guess classification vs regression from the label values."""
    import pandas as pd

    non_null = series.dropna()
    if not pd.api.types.is_numeric_dtype(series.dtype) or pd.api.types.is_bool_dtype(series.dtype):
        return "classification"
    n_unique = int(non_null.nunique())
    if series.dtype.kind == "f" and not (non_null == non_null.round()).all():
        return "regression"  # non-integer floats
    if n_unique > max(20, int(0.05 * len(non_null))):
        return "regression"
    return "classification"


def label_health(series, task: str | None) -> dict:
    health: dict = {}
    null_count = int(series.isnull().sum())
    health["null_rate"] = _safe_rate(null_count, len(series))
    if task in (None, "auto"):
        task = infer_label_task(series)
    health["task"] = task

    if task == "regression":
        values = series.dropna().astype(float)
        health.update({
            "unique_count": int(values.nunique()),
            "min": _safe_float(values.min()) if len(values) else None,
            "max": _safe_float(values.max()) if len(values) else None,
            "mean": _safe_float(values.mean()) if len(values) else None,
            "std": _safe_float(values.std()) if len(values) else None,
            "p01": _safe_float(values.quantile(0.01)) if len(values) else None,
            "p50": _safe_float(values.quantile(0.50)) if len(values) else None,
            "p99": _safe_float(values.quantile(0.99)) if len(values) else None,
            "skew": _safe_float(values.skew()) if len(values) > 2 else None,
        })
        return health

    if task == "classification":
        counts = series.value_counts(normalize=True)
        health["num_classes"] = int(series.nunique())
        health["class_distribution"] = {
            str(k): round(float(v), 4) for k, v in counts.head(MAX_CLASSES_REPORTED).items()
        }
        if len(counts) > MAX_CLASSES_REPORTED:
            health["class_distribution_truncated"] = True
        if len(counts) > 1 and float(counts.min()) > 0:
            health["imbalance_ratio"] = round(float(counts.max() / counts.min()), 2)
        elif len(counts) == 1:
            health["imbalance_ratio"] = 1.0
        else:
            health["imbalance_ratio"] = None
        rare = [str(k) for k, v in counts.items() if v < 0.005]
        health["rare_class_count"] = len(rare)
        health["rare_classes"] = rare[:MAX_CLASSES_REPORTED]

    return health


def profile(df, args: argparse.Namespace, fmt: str, nested_cols: list[str] | None = None) -> dict:
    nested_cols = nested_cols or []
    result: dict = {
        "path": args.path,
        "format": fmt,
        "num_rows": len(df),
        "num_cols": len(df.columns),
        "nested_columns": nested_cols,
        "columns": [profile_column(df[c], str(c), nested=str(c) in nested_cols) for c in df.columns],
        "duplicate_row_count": int(df.duplicated().sum()),
        "duplicate_row_rate": _safe_rate(int(df.duplicated().sum()), len(df)),
    }

    if args.label_col and args.label_col in df.columns:
        result["label_health"] = label_health(df[args.label_col], task=args.task)

    if args.id_col and args.id_col in df.columns:
        dup_ids = df[args.id_col].duplicated().sum()
        result["id_col_stats"] = {
            "duplicate_ids": int(dup_ids),
            "duplicate_id_rate": _safe_rate(int(dup_ids), len(df)),
        }

    if args.text_col and args.text_col in df.columns:
        word_lengths = df[args.text_col].dropna().astype(str).str.split().str.len()
        result["text_col_stats"] = {
            "p50_words": _safe_float(word_lengths.quantile(0.50)) if len(word_lengths) > 0 else None,
            "p95_words": _safe_float(word_lengths.quantile(0.95)) if len(word_lengths) > 0 else None,
            "p99_words": _safe_float(word_lengths.quantile(0.99)) if len(word_lengths) > 0 else None,
            "empty_rate": _safe_rate(int((word_lengths == 0).sum()), len(word_lengths)),
        }

    return result


def main() -> None:
    args = parse_args()

    fmt = args.format if args.format != "auto" else detect_format(args.path)

    try:
        import pandas  # noqa: F401
    except ImportError:
        print(
            json.dumps({"error": "pandas is required: uv add pandas pyarrow"}),
            file=sys.stderr,
        )
        sys.exit(1)

    if not Path(args.path).exists():
        print(json.dumps({"error": f"path not found: {args.path}"}), file=sys.stderr)
        sys.exit(1)
    try:
        df = load_dataframe(args.path, fmt, args.sample)
    except (ValueError, OSError) as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)
    nested_cols = flatten_nested_columns(df)
    stats = profile(df, args, fmt, nested_cols)

    output_json = json.dumps(_sanitize_for_json(stats), indent=2, default=str, allow_nan=False)
    if args.output:
        Path(args.output).write_text(output_json)
        print(f"Profile written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
