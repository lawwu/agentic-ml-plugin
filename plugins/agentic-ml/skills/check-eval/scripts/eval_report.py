#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "numpy>=1.24",
#   "pandas>=2.0",
#   "pyarrow>=14",  # parquet engine for --slices *.parquet
# ]
# ///
"""Metrics with bootstrap confidence intervals from a predictions file.

Predictions CSV (shared contract): row_key, y_true, plus
  binary      y_score (probability of the positive class), optional y_pred
  multiclass  score_<class> columns and/or y_pred
  regression  y_pred

Metrics (* = lower is better):
  binary      auprc roc_auc f1 precision recall accuracy brier* log_loss*
  multiclass  accuracy f1_macro log_loss*
  regression  rmse* mae* r2 mape*   (mape is a fraction; skipped when y_true has zeros)

Reports the point estimate and a percentile bootstrap CI (rows resampled with replacement;
resamples with a single class are skipped and counted). With --baseline-pred the files are
inner-joined on row_key and a paired bootstrap gives delta = model - baseline on the same
resampled rows. "significant" means the delta CI excludes 0 in the better direction.

Hard predictions for f1/precision/recall/accuracy come from y_pred when present and no
--threshold is given; otherwise from y_score >= threshold (default 0.5).

Binary labels may be bool, 0/1, or strings such as True/False, yes/no; pass --pos-label for
anything else. Rows with a missing label or prediction are dropped (and counted in warnings).

With --split-manifest/--expect-split, the prediction row_keys must equal that split's rows in
split_assignments.csv; for test, they must also hash to the manifest's test_keys_sha256.

Output JSON: metric, task, higher_is_better, n, n_positive, point, ci, ci_level, n_boot,
degenerate_resamples, baseline {point, ci}, delta {point, ci, model_better, significant,
prob_not_better}, secondary {name: {point, ci}}, threshold, calibration {brier, ece, bins},
threshold_table, slices [{column, value, n, point, ci, flagged | skipped}], split_check, warnings.

Examples:
  uv run eval_report.py --pred model_val.csv --metric auprc --baseline-pred base_val.csv \\
      --slices data.csv --slice-cols region,plan --key-col customer_id --threshold-grid \\
      --split-manifest out/splits/split-manifest.json --expect-split val --out eval-val.json
  uv run eval_report.py --pred model_val.csv --metric rmse --out eval-val.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

MISSING = "__missing__"
ROW_INDEX = "__row_index__"
TRUE_TOKENS = {"true", "t", "yes", "y", "1", "positive", "pos"}
FALSE_TOKENS = {"false", "f", "no", "n", "0", "negative", "neg"}
EPS = 1e-15
MIN_SLICE_N, MIN_POS = 30, 30


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def canon(v) -> str | None:
    """Stable string form: NaN -> None, 1.0 -> '1', numpy True -> 'True'."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v)


def binary_token(v) -> str | None:
    """canon() plus true/false spellings collapsed to '1'/'0'."""
    c = canon(v)
    if c is None:
        return None
    low = c.strip().lower()
    return "1" if low in TRUE_TOKENS else "0" if low in FALSE_TOKENS else c


def keys_sha256(keys) -> str:
    """sha256 of sorted string keys joined by newline (contract shared with make_splits.py)."""
    return hashlib.sha256("\n".join(sorted(map(str, keys))).encode()).hexdigest()


def read_table(path: str, key: str | None = None) -> pd.DataFrame:
    p = Path(path)
    if not p.is_file():
        die(f"file not found: {path}")
    if p.name.lower().endswith((".parquet", ".pq")):
        df = pd.read_parquet(p)
        if key and key in df:
            df[key] = [canon(v) for v in df[key]]
        return df
    return pd.read_csv(p, dtype={key: str} if key else None, low_memory=False)


def to_binary(s: pd.Series, pos_label: str | None) -> np.ndarray:
    """Labels -> 1.0/0.0, NaN stays NaN."""
    c = pd.Series([canon(v) for v in s], dtype=object)
    out = np.full(len(c), np.nan)
    ok = c.notna().to_numpy()
    if pos_label is not None:
        out[ok] = (c[ok] == pos_label).to_numpy(dtype=float)
        return out
    low = c[ok].str.strip().str.lower()
    pos, neg = low.isin(TRUE_TOKENS), low.isin(FALSE_TOKENS)
    if not (pos | neg).all():
        die(f"cannot map labels {sorted(set(low[~(pos | neg)]))[:5]} in {s.name!r} to 0/1; pass --pos-label")
    out[ok] = pos.to_numpy(dtype=float)
    return out


# ---- metrics: each takes a dict of aligned arrays (y, s, yp, P) ---------------------------

def _rank(x: np.ndarray) -> np.ndarray:
    """Average ranks (1-based), ties share the mean rank."""
    o = np.argsort(x, kind="mergesort")
    xs = x[o]
    starts = np.r_[0, np.flatnonzero(xs[1:] != xs[:-1]) + 1]
    sizes = np.diff(np.r_[starts, len(x)])
    r = np.empty(len(x))
    r[o] = np.repeat(starts + (sizes + 1) / 2, sizes)
    return r


def roc_auc(y, s) -> float:
    npos = y.sum()
    nneg = len(y) - npos
    if npos == 0 or nneg == 0:
        return np.nan
    return float((_rank(s)[y == 1].sum() - npos * (npos + 1) / 2) / (npos * nneg))


def average_precision(y, s) -> float:
    """Step-wise AP (sklearn's average_precision_score), ties grouped by distinct score."""
    if y.sum() == 0:
        return np.nan
    o = np.argsort(-s, kind="mergesort")
    ys, ss = y[o], s[o]
    last = np.r_[ss[1:] != ss[:-1], True]
    tp = np.cumsum(ys)[last]
    k = np.arange(1, len(ys) + 1)[last]
    rec = tp / tp[-1]
    return float(np.sum(np.diff(np.r_[0.0, rec]) * tp / k))


def confusion(y, yp):
    tp = float(np.sum((yp == 1) & (y == 1)))
    fp = float(np.sum((yp == 1) & (y == 0)))
    fn = float(np.sum((yp == 0) & (y == 1)))
    return tp, fp, fn, float(len(y)) - tp - fp - fn


def prf(y, yp):
    tp, fp, fn, _ = confusion(y, yp)
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    f = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 0.0
    return p, r, f


def bin_log_loss(y, s) -> float:
    s = np.clip(s, EPS, 1 - EPS)
    return float(-np.mean(y * np.log(s) + (1 - y) * np.log(1 - s)))


def mc_log_loss(y, P) -> float:
    P = P / P.sum(axis=1, keepdims=True)
    return float(-np.mean(np.log(np.clip(P[np.arange(len(y)), y], EPS, 1))))


def f1_macro(y, yp) -> float:
    k = int(max(y.max(), yp.max())) + 1
    tp = np.bincount(y[y == yp], minlength=k)
    denom = np.bincount(y, minlength=k) + np.bincount(yp, minlength=k)
    present = denom > 0
    return float(np.mean(2 * tp[present] / denom[present]))


def r2(y, p) -> float:
    ss = np.sum((y - y.mean()) ** 2)
    return float(1 - np.sum((y - p) ** 2) / ss) if ss > 0 else np.nan


# name -> (function of data dict, required input key)
METRICS = {
    "binary": {
        "auprc": (lambda d: average_precision(d["y"], d["s"]), "s"),
        "roc_auc": (lambda d: roc_auc(d["y"], d["s"]), "s"),
        "f1": (lambda d: prf(d["y"], d["yp"])[2], "yp"),
        "precision": (lambda d: prf(d["y"], d["yp"])[0], "yp"),
        "recall": (lambda d: prf(d["y"], d["yp"])[1], "yp"),
        "accuracy": (lambda d: float(np.mean(d["y"] == d["yp"])), "yp"),
        "brier": (lambda d: float(np.mean((d["s"] - d["y"]) ** 2)), "s"),
        "log_loss": (lambda d: bin_log_loss(d["y"], d["s"]), "s"),
    },
    "multiclass": {
        "accuracy": (lambda d: float(np.mean(d["y"] == d["yp"])), "yp"),
        "f1_macro": (lambda d: f1_macro(d["y"], d["yp"]), "yp"),
        "log_loss": (lambda d: mc_log_loss(d["y"], d["P"]), "P"),
    },
    "regression": {  # predictions live in d["s"]
        "rmse": (lambda d: float(np.sqrt(np.mean((d["y"] - d["s"]) ** 2))), "s"),
        "mae": (lambda d: float(np.mean(np.abs(d["y"] - d["s"]))), "s"),
        "r2": (lambda d: r2(d["y"], d["s"]), "s"),
        "mape": (lambda d: float(np.mean(np.abs(d["y"] - d["s"]) / np.abs(d["y"]))), "s"),
    },
}
LOWER_IS_BETTER = {"brier", "log_loss", "rmse", "mae", "mape"}
UNIT_RANGE = {"auprc", "roc_auc", "f1", "precision", "recall", "accuracy", "brier", "f1_macro"}
DEFAULT_SECONDARY = {"binary": ["auprc", "roc_auc", "brier"], "multiclass": ["accuracy", "f1_macro", "log_loss"],
                     "regression": ["rmse", "mae", "r2"]}


def detect_task(df: pd.DataFrame, metric: str) -> str:
    for task, names in (("regression", {"rmse", "mae", "r2", "mape"}), ("multiclass", {"f1_macro"})):
        if metric in names:
            return task
    if "y_score" in df:
        return "binary"
    if any(c.startswith("score_") for c in df.columns):
        return "multiclass"
    if metric in {"auprc", "roc_auc", "f1", "precision", "recall", "brier"}:
        return "binary"
    y = df["y_true"].dropna()
    numeric = pd.api.types.is_numeric_dtype(y) and not pd.api.types.is_bool_dtype(y)
    if numeric and (y.nunique() > 10 or not np.all(np.mod(y, 1) == 0)):
        return "regression"
    return "binary" if y.nunique() <= 2 else "multiclass"


def prepare(df: pd.DataFrame, task: str, args, classes: list[str] | None, suffix: str = ""):
    """Arrays for one predictions source. Returns (data dict with NaN for missing, threshold source)."""
    def col(c):
        return df.get(c + suffix)

    yt = df["y_true"]
    d = {"y": None, "s": None, "yp": None, "P": None}
    src = None
    if task == "binary":
        d["y"] = to_binary(yt, args.pos_label)
        if col("y_score") is not None:
            d["s"] = pd.to_numeric(col("y_score"), errors="coerce").to_numpy(dtype=float)
        if col("y_pred") is not None and args.threshold is None:
            d["yp"], src = to_binary(col("y_pred"), args.pos_label), "y_pred column"
        elif d["s"] is not None:
            thr = 0.5 if args.threshold is None else args.threshold
            d["yp"] = np.where(np.isnan(d["s"]), np.nan, (d["s"] >= thr).astype(float))
            src = f"y_score >= {thr}"
    elif task == "multiclass":
        idx = {c: i for i, c in enumerate(classes)}
        def code(s):
            return np.array([idx.get(canon(v), np.nan) for v in s], dtype=float)

        d["y"] = code(yt)
        if all(col(f"score_{c}") is not None for c in classes):
            d["P"] = np.column_stack([pd.to_numeric(col(f"score_{c}"), errors="coerce") for c in classes]).astype(float)
        if col("y_pred") is not None:
            d["yp"], src = code(col("y_pred")), "y_pred column"
        elif d["P"] is not None:
            bad = np.isnan(d["P"]).any(axis=1)
            d["yp"] = np.where(bad, np.nan, np.argmax(np.nan_to_num(d["P"], nan=-1), axis=1))
            src = "argmax of score_<class>"
    else:
        d["y"] = pd.to_numeric(yt, errors="coerce").to_numpy(dtype=float)
        if col("y_pred") is not None:
            d["s"] = pd.to_numeric(col("y_pred"), errors="coerce").to_numpy(dtype=float)
    return d, src


def ci_of(a: np.ndarray, level: float):
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return None
    return [float(np.percentile(a, 50 * (1 - level))), float(np.percentile(a, 50 * (1 + level)))]


def is_degenerate(task: str, y: np.ndarray) -> bool:
    """A classification sample with a single class (regression samples are never skipped)."""
    return len(y) == 0 or (task != "regression" and y.min() == y.max())


def bootstrap(D: dict, fns: dict, n_boot: int, rng, task: str):
    """Resample rows with replacement; every fn sees the same rows (paired). NaN marks skipped."""
    n = len(D["y"])
    res = {k: np.full(n_boot, np.nan) for k in fns}
    deg = 0
    for b in range(n_boot):
        idx = rng.integers(0, n, n)
        sub = {k: (v[idx] if v is not None else None) for k, v in D.items()}
        if is_degenerate(task, sub["y"]):
            deg += 1
            continue
        for k, fn in fns.items():
            res[k][b] = fn(sub)
    return {k: np.round(v, 12) for k, v in res.items()}, deg  # rounding drops float noise in paired deltas


def fnum(x):
    return None if x is None or not np.isfinite(x) else round(float(x), 12)


def clean(o):
    """JSON-safe: numpy -> python, NaN/inf -> null."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return fnum(float(o))
    if isinstance(o, np.bool_):
        return bool(o)
    return o


def calibration(y, s) -> dict:
    """10 equal-width bins on [0, 1]; ECE = sum(n_b / N * |mean_pred_b - frac_pos_b|)."""
    b = np.clip(np.digitize(s, np.linspace(0.1, 0.9, 9)), 0, 9)
    bins, ece = [], 0.0
    for i in range(10):
        m = b == i
        k = int(m.sum())
        mp = float(s[m].mean()) if k else None
        fp = float(y[m].mean()) if k else None
        if k:
            ece += k / len(y) * abs(mp - fp)
        bins.append({"bin_low": round(i / 10, 2), "bin_high": round((i + 1) / 10, 2), "n": k,
                     "mean_pred": mp, "frac_pos": fp})
    return {"brier": float(np.mean((s - y) ** 2)), "ece": ece, "n_bins": 10, "bins": bins}


def threshold_table(y, s, thresholds) -> list[dict]:
    rows = []
    for t in thresholds:
        tp, fp, fn, tn = confusion(y, (s >= t).astype(float))
        rows.append({"threshold": round(float(t), 4),
                     "precision": tp / (tp + fp) if tp + fp else None,
                     "recall": tp / (tp + fn) if tp + fn else None,
                     "f1": 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None,
                     "flagged_rate": (tp + fp) / len(y), "tp": int(tp), "fp": int(fp), "fn": int(fn), "tn": int(tn)})
    return rows


def split_check(pred_keys: pd.Series, manifest_path: str, expect: str) -> dict:
    mp = Path(manifest_path)
    if not mp.is_file():
        die(f"split manifest not found: {manifest_path}")
    m = json.loads(mp.read_text())
    ap = Path(m.get("assignments_path", "split_assignments.csv"))
    # assignments_path is relative to make_splits' --out-dir (the manifest's parent); also accept
    # paths relative to the manifest directory or absolute ones.
    cands = [ap] if ap.is_absolute() else [mp.parent / ap, mp.parent.parent / ap, mp.parent / ap.name]
    path = next((p for p in cands if p.is_file()), None)
    if path is None:
        die(f"assignments file not found (tried {[str(c) for c in cands]})")
    a = pd.read_csv(path, dtype={"row_key": str, "split": str})
    expected = set(a.loc[a["split"] == expect, "row_key"])
    got = set(pred_keys)
    missing, extra = expected - got, got - expected
    extra_by_split = a.loc[a["row_key"].isin(extra), "split"].value_counts().to_dict()
    unknown = len(extra - set(a["row_key"]))
    if unknown:
        extra_by_split["not_in_assignments"] = unknown
    res = {"expected_split": expect, "matches": not missing and not extra, "n_expected": len(expected),
           "n_pred": len(got), "n_missing": len(missing), "n_extra": len(extra), "extra_by_split": extra_by_split,
           "test_keys_sha256_match": None, "assignments_path": str(path.resolve())}
    if expect == "test":
        res["test_keys_sha256_match"] = keys_sha256(got) == m.get("test_keys_sha256")
        res["assignments_test_sha256_match"] = keys_sha256(expected) == m.get("test_keys_sha256")
    return res


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pred", required=True, help="predictions CSV (row_key, y_true, y_score|score_<c>|y_pred)")
    ap.add_argument("--metric", required=True, help="primary metric (see list above)")
    ap.add_argument("--baseline-pred", help="baseline predictions CSV for a paired comparison")
    ap.add_argument("--task", default="auto", choices=["auto", "binary", "multiclass", "regression"])
    ap.add_argument("--secondary", help="comma-separated extra metrics (default: a standard set for the task; "
                    "'none' to skip)")
    ap.add_argument("--threshold", type=float, help="decision threshold on y_score (default 0.5 or y_pred)")
    ap.add_argument("--threshold-grid", action="store_true", help="threshold table for 0.05..0.95 by 0.05")
    ap.add_argument("--pos-label", help="positive class for binary labels that are not bool/0-1/yes-no")
    ap.add_argument("--slices", help="CSV/Parquet with slice columns, joined on --key-col == row_key")
    ap.add_argument("--slice-cols", help="comma-separated slice columns (numeric with >20 values -> quintiles)")
    ap.add_argument("--key-col", default="row_key", help=f"key column in --slices ({ROW_INDEX} = 0-based row index)")
    ap.add_argument("--n-boot", type=int, default=2000)
    ap.add_argument("--ci", type=float, default=0.95)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--split-manifest", help="split-manifest.json from make_splits.py")
    ap.add_argument("--expect-split", choices=["train", "val", "test"], help="split the predictions should cover")
    ap.add_argument("--out", required=True, help="output JSON path")
    args = ap.parse_args(argv)

    if not 0 < args.ci < 1 or args.n_boot < 0:
        die("need 0 < --ci < 1 and --n-boot >= 0")
    if bool(args.slices) != bool(args.slice_cols):
        die("--slices and --slice-cols go together")
    if bool(args.split_manifest) != bool(args.expect_split):
        die("--split-manifest and --expect-split go together")
    warns: list[str] = []

    M = read_table(args.pred, "row_key")
    for c in ("row_key", "y_true"):
        if c not in M:
            die(f"{args.pred} has no {c!r} column (columns: {list(M.columns)[:20]})")
    if len(M) == 0:
        die(f"{args.pred} has no rows")
    if M["row_key"].isna().any() or M["row_key"].duplicated().any():
        die(f"{args.pred}: row_key must be unique and non-null")
    pred_keys = M["row_key"].copy()
    task = args.task if args.task != "auto" else detect_task(M, args.metric)
    if args.metric not in METRICS[task]:
        die(f"metric {args.metric!r} not available for {task}; choose from {sorted(METRICS[task])}")
    higher = args.metric not in LOWER_IS_BETTER

    classes = None
    if task == "multiclass":
        sc = [c[len("score_"):] for c in M.columns if c.startswith("score_")]
        vals = {canon(v) for c in ("y_true", "y_pred") if c in M for v in M[c]} - {None}
        if sc:
            classes = sc
            unknown = vals - set(sc)
            if unknown:
                die(f"labels {sorted(unknown)[:5]} have no score_<class> column")
        else:
            classes = sorted(vals)

    J = M
    n_model = len(M)
    if args.baseline_pred:
        B = read_table(args.baseline_pred, "row_key")
        if "row_key" not in B or B["row_key"].duplicated().any():
            die(f"{args.baseline_pred}: needs a unique row_key column")
        n_base = len(B)
        B = B.rename(columns={c: c + "__base" for c in B.columns if c != "row_key"})
        J = M.merge(B, on="row_key", how="inner")
        if len(J) != n_model or len(J) != n_base:
            warns.append(f"baseline/model row mismatch: model {n_model}, baseline {n_base}, joined {len(J)}; "
                         f"comparison uses the {len(J)} shared rows")
        if len(J) == 0:
            die("model and baseline predictions share no row_key")
        if "y_true__base" in J:
            # binary files may spell the same label differently (True vs 1), so compare mapped values
            norm = binary_token if task == "binary" and args.pos_label is None else canon
            a, b = [pd.Series([norm(v) for v in J[c]]) for c in ("y_true", "y_true__base")]
            n_diff = int(((a != b) & a.notna() & b.notna()).sum())
            if n_diff:
                warns.append(f"{n_diff} rows have different y_true in model and baseline files; using the model's")

    D, thr_src = prepare(J, task, args, classes)
    need = METRICS[task][args.metric][1]
    need_txt = {"s": "y_pred" if task == "regression" else "y_score", "P": "score_<class> columns",
                "yp": "y_pred or y_score" if task == "binary" else "y_pred or score_<class> columns"}[need]
    if D[need] is None:
        die(f"{args.metric} ({task}) needs {need_txt} in {args.pred}")
    if args.baseline_pred:
        Bd, _ = prepare(J, task, args, classes, suffix="__base")  # y_true always from the model file
        if Bd[need] is None:
            die(f"{args.metric} ({task}) needs {need_txt} in {args.baseline_pred}")
        D.update({"b" + k: v for k, v in Bd.items() if k != "y"})

    # Drop rows with missing labels or predictions
    arrays = [v for v in D.values() if v is not None]
    ok = np.all([~np.isnan(v) if v.ndim == 1 else ~np.isnan(v).any(axis=1) for v in arrays], axis=0)
    if (~ok).sum():
        warns.append(f"dropped {int((~ok).sum())} rows with missing y_true or predictions")
    D = {k: (v[ok] if v is not None else None) for k, v in D.items()}
    keys = J["row_key"].to_numpy()[ok]
    n = len(D["y"])
    if n == 0:
        die("no rows left after dropping missing values")
    for k in ("y", "yp", "byp"):
        if task == "multiclass" and D.get(k) is not None:
            D[k] = D[k].astype(int)
    if task == "binary" and D["s"] is not None and ((D["s"] < 0) | (D["s"] > 1)).any():
        warns.append("y_score has values outside [0, 1]; brier, log_loss and calibration assume probabilities")

    def available(name: str) -> str | None:
        if name not in METRICS[task]:
            return f"not a {task} metric"
        if D[METRICS[task][name][1]] is None:
            return "required prediction column missing"
        if name == "mape" and np.any(D["y"] == 0):
            return "y_true contains zeros"
        return None

    def base_fn(fn):
        return lambda d: fn({"y": d["y"], "s": d["bs"], "yp": d["byp"], "P": d["bP"]})

    if args.secondary and args.secondary.strip().lower() == "none":
        sec_names = []
    elif args.secondary:
        sec_names = [s.strip() for s in args.secondary.split(",") if s.strip()]
    else:
        sec_names = [s for s in DEFAULT_SECONDARY[task] if available(s) is None]
    sec_names = [s for s in dict.fromkeys(sec_names) if s != args.metric]
    for s in list(sec_names):
        why = available(s)
        if why:
            warns.append(f"secondary metric {s} skipped: {why}")
            sec_names.remove(s)

    primary_ok = available(args.metric)
    fns = {}
    if primary_ok is None:
        fns["model"] = METRICS[task][args.metric][0]
        if args.baseline_pred:
            fns["baseline"] = base_fn(METRICS[task][args.metric][0])
    else:
        warns.append(f"primary metric {args.metric} not computed: {primary_ok}")
    for s in sec_names:
        fns["sec:" + s] = METRICS[task][s][0]

    points = {k: fnum(fn(D)) for k, fn in fns.items()}
    boots, deg = bootstrap(D, fns, args.n_boot, np.random.default_rng(args.seed), task)
    cis = {k: ci_of(v, args.ci) for k, v in boots.items()}

    point, ci = points.get("model"), cis.get("model")
    baseline = delta = None
    if "baseline" in fns:
        baseline = {"point": points["baseline"], "ci": cis["baseline"]}
        d_boot = boots["model"] - boots["baseline"]
        d_point = None if point is None or points["baseline"] is None else point - points["baseline"]
        d_ci = ci_of(d_boot, args.ci)
        valid = d_boot[~np.isnan(d_boot)]
        delta = {"point": d_point, "ci": d_ci,
                 "model_better": None if d_point is None else (d_point > 0 if higher else d_point < 0),
                 "significant": None if d_ci is None else (d_ci[0] > 0 if higher else d_ci[1] < 0),
                 "prob_not_better": float(np.mean(valid <= 0 if higher else valid >= 0)) if len(valid) else None}

    n_pos = int(D["y"].sum()) if task == "binary" else None
    calib = thr_table = None
    thr_used = None
    if task == "binary":
        if n_pos < MIN_POS:
            warns.append(f"only {n_pos} positives (< {MIN_POS}); the interval is too wide to support a decision")
        if D["s"] is not None:
            calib = calibration(D["y"], D["s"])
            grid = np.round(np.arange(0.05, 0.951, 0.05), 2) if args.threshold_grid else \
                [0.5 if args.threshold is None else args.threshold]
            thr_table = threshold_table(D["y"], D["s"], grid)
        thr_value = None if thr_src == "y_pred column" else 0.5 if args.threshold is None else args.threshold
        thr_used = {"value": thr_value, "source": thr_src}
    if ci and args.metric in UNIT_RANGE and ci[1] - ci[0] > 0.1:
        warns.append(f"{args.metric} CI width {ci[1] - ci[0]:.3f} > 0.1; the estimate is imprecise")
    if args.n_boot and deg > 0.05 * args.n_boot:
        warns.append(f"{deg}/{args.n_boot} bootstrap resamples had a single class and were skipped")

    # Slices
    slices = []
    if args.slices and primary_ok is None:
        S = read_table(args.slices, None if args.key_col == ROW_INDEX else args.key_col)
        if args.key_col == ROW_INDEX:
            S[ROW_INDEX] = np.arange(len(S)).astype(str)
        if args.key_col not in S:
            die(f"--key-col {args.key_col!r} not in {args.slices}")
        S[args.key_col] = [canon(v) for v in S[args.key_col]]
        if S[args.key_col].duplicated().any():
            die(f"--key-col {args.key_col!r} is not unique in {args.slices}")
        cols = [c.strip() for c in args.slice_cols.split(",") if c.strip()]
        missing_cols = [c for c in cols if c not in S]
        if missing_cols:
            die(f"slice columns {missing_cols} not in {args.slices}")
        S = S.set_index(args.key_col)[cols].reindex(keys)
        n_unmatched = int(S.isna().all(axis=1).sum())
        if n_unmatched:
            warns.append(f"{n_unmatched} prediction rows have no match in {args.slices} on {args.key_col}")
        fn = METRICS[task][args.metric][0]
        for ci_, c in enumerate(cols):
            v = S[c].reset_index(drop=True)
            if pd.api.types.is_numeric_dtype(v) and not pd.api.types.is_bool_dtype(v) and v.nunique() > 20:
                q = pd.qcut(v, 5, duplicates="drop")
                names = [f"q{i + 1} ({iv.left:.4g}, {iv.right:.4g}]" for i, iv in enumerate(q.cat.categories)]
                v = q.cat.rename_categories(names).astype(object)
            lab = np.array([canon(x) or MISSING for x in v], dtype=object)
            vc = pd.Series(lab).value_counts()
            n_skipped = 0
            for vi, (val, k) in enumerate(vc.items()):
                entry = {"column": c, "value": val, "n": int(k)}
                m = lab == val
                if task == "binary":
                    entry["n_positive"] = int(D["y"][m].sum())
                sub = {kk: (vv[m] if vv is not None else None) for kk, vv in D.items()}
                why = f"n < {MIN_SLICE_N}" if k < MIN_SLICE_N else "single class" if is_degenerate(task, sub["y"]) else None
                if why:
                    n_skipped += 1
                    if n_skipped <= 20:
                        slices.append({**entry, "skipped": why})
                    continue
                p = fnum(fn(sub))
                b, _ = bootstrap(sub, {"m": fn}, args.n_boot, np.random.default_rng([args.seed, ci_, vi]), task)
                sci = ci_of(b["m"], args.ci)
                flagged = None
                if sci and point is not None:
                    flagged = sci[1] < point if higher else sci[0] > point
                slices.append({**entry, "point": p, "ci": sci, "flagged": flagged})
            if n_skipped > 20:
                warns.append(f"slice column {c}: {n_skipped} values skipped (first 20 listed)")
        flagged = [f"{s['column']}={s['value']}" for s in slices if s.get("flagged")]
        if flagged:
            warns.append(f"slices below the overall {args.metric}: {flagged[:10]}")

    # Split check
    sc_res = None
    if args.split_manifest:
        sc_res = split_check(pred_keys, args.split_manifest, args.expect_split)
        if not sc_res["matches"]:
            warns.append(f"SPLIT CHECK FAILED: predictions do not cover exactly the {args.expect_split} split "
                         f"({sc_res['n_missing']} missing, {sc_res['n_extra']} extra: {sc_res['extra_by_split']})")
        if sc_res["test_keys_sha256_match"] is False:
            warns.append("SPLIT CHECK FAILED: prediction keys do not hash to the manifest's test_keys_sha256")
        if sc_res.get("assignments_test_sha256_match") is False:
            warns.append("SPLIT CHECK FAILED: split_assignments.csv test rows no longer match the manifest hash")

    out = {
        "metric": args.metric, "task": task, "higher_is_better": higher, "n": n, "n_positive": n_pos,
        "point": point, "ci": ci, "ci_level": args.ci, "n_boot": args.n_boot, "degenerate_resamples": deg,
        "baseline": baseline, "delta": delta,
        "secondary": {s: {"point": points["sec:" + s], "ci": cis["sec:" + s]} for s in sec_names},
        "threshold": thr_used, "calibration": calib, "threshold_table": thr_table, "slices": slices,
        "split_check": sc_res, "warnings": warns,
        "inputs": {"pred": str(Path(args.pred).resolve()),
                   "baseline_pred": str(Path(args.baseline_pred).resolve()) if args.baseline_pred else None,
                   "slices": str(Path(args.slices).resolve()) if args.slices else None, "seed": args.seed},
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(clean(out), indent=2) + "\n")

    def f(x):
        return "n/a" if x is None else f"{x:.4f}"

    def fci(c):
        return "[n/a]" if not c else f"[{c[0]:.4f}, {c[1]:.4f}]"

    pos_txt = f", {n_pos} positives" if n_pos is not None else ""
    print(f"{args.metric} = {f(point)} {fci(ci)}  ({args.ci:.0%} CI, {task}, n={n}{pos_txt}, {args.n_boot} resamples)")
    if delta:
        verdict = "significant" if delta["significant"] else "not significant"
        print(f"  baseline {f(baseline['point'])} {fci(baseline['ci'])}; delta {f(delta['point'])} {fci(delta['ci'])} "
              f"-> {'better' if delta['model_better'] else 'not better'}, {verdict}, "
              f"P(not better) = {f(delta['prob_not_better'])}")
    for s in sec_names:
        print(f"  {s} = {f(points['sec:' + s])} {fci(cis['sec:' + s])}")
    if calib:
        print(f"  calibration: brier {calib['brier']:.4f}, ECE {calib['ece']:.4f}")
    evaluated = [s for s in slices if "point" in s]
    if evaluated:
        print(f"  slices: {len(evaluated)} evaluated, {sum(1 for s in evaluated if s['flagged'])} flagged, "
              f"{sum(1 for s in slices if 'skipped' in s)} skipped (n < {MIN_SLICE_N} or single class)")
    if sc_res:
        hash_txt = "" if sc_res["test_keys_sha256_match"] is None else f", test hash match {sc_res['test_keys_sha256_match']}"
        print(f"  split check ({args.expect_split}): {'OK' if sc_res['matches'] else 'MISMATCH'}{hash_txt}")
    for w in warns:
        print(f"  WARNING: {w}", file=sys.stderr if w.startswith("SPLIT CHECK FAILED") else sys.stdout)
    print(f"  -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
