#!/usr/bin/env -S uv run python
"""
profile-dataset.py — statistical profiling script for the dataset-audit skill.
Usage: uv run profile-dataset.py <path> [--format csv|parquet|jsonl] [--label-col COL]
                                          [--text-col COL] [--id-col COL] [--sample N]
                                          [--output OUTPUT.json]

Outputs a JSON stats object to --output (default: stdout).
"""

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
            import glob
            files = sorted(glob.glob(str(p / "*.parquet")))
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


def profile_column(series, col_name: str) -> dict:
    """Compute per-column stats."""
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

    if series.dtype.kind in ("i", "u", "f"):  # numeric
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

    elif series.dtype == object or str(series.dtype) == "string":  # text
        lengths = series.dropna().astype(str).str.len()
        stats.update({
            "min_len": int(lengths.min()) if len(lengths) > 0 else None,
            "max_len": int(lengths.max()) if len(lengths) > 0 else None,
            "mean_len": round(float(lengths.mean()), 1) if len(lengths) > 0 else None,
            "p95_len": round(float(lengths.quantile(0.95)), 1) if len(lengths) > 0 else None,
            "top_values": series.value_counts().head(5).to_dict() if 0 < stats["unique_count"] <= 100 else None,
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


def label_health(series, task: str | None) -> dict:
    health: dict = {}
    null_count = int(series.isnull().sum())
    health["null_rate"] = _safe_rate(null_count, len(series))

    if task in ("classification", None):
        counts = series.value_counts(normalize=True)
        health["class_distribution"] = {str(k): round(float(v), 4) for k, v in counts.items()}
        health["num_classes"] = int(series.nunique())
        if len(counts) > 1 and float(counts.min()) > 0:
            health["imbalance_ratio"] = round(float(counts.max() / counts.min()), 2)
        elif len(counts) == 1:
            health["imbalance_ratio"] = 1.0
        else:
            health["imbalance_ratio"] = None
        health["rare_classes"] = [str(k) for k, v in counts.items() if v < 0.005]

    return health


def profile(df, args: argparse.Namespace) -> dict:
    result: dict = {
        "path": args.path,
        "format": args.format if args.format != "auto" else "auto-detected",
        "num_rows": len(df),
        "num_cols": len(df.columns),
        "columns": [profile_column(df[c], c) for c in df.columns],
        "duplicate_row_count": int(df.duplicated().sum()),
        "duplicate_row_rate": _safe_rate(int(df.duplicated().sum()), len(df)),
    }

    if args.label_col and args.label_col in df.columns:
        result["label_health"] = label_health(df[args.label_col], task=None)

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

    df = load_dataframe(args.path, fmt, args.sample)
    stats = profile(df, args)

    output_json = json.dumps(_sanitize_for_json(stats), indent=2, default=str, allow_nan=False)
    if args.output:
        Path(args.output).write_text(output_json)
        print(f"Profile written to: {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
