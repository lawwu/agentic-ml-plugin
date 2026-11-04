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
serving_check.py: catch training/serving skew before promotion (check-deployment-readiness skill).

Loads the saved model fresh from disk (as a serving process would), rebuilds the raw input rows
for every row_key in a reference predictions file (label dropped), re-scores them, and reports:
  parity      re-scored outputs match the reference within --atol (y_score, score_*, or y_pred)
  contract    optional: required feature columns and dtype kinds match data-contract.json
  latency     single-row p50/p95/p99 vs --latency-budget-ms, plus batch throughput
  footprint   model file size and peak RSS

Example:
  uv run serving_check.py --model out/train/model.joblib --data data.csv \\
      --ref-pred out/train/predictions/model_val.csv --label-col churned \\
      --contract out/contract/data-contract.json --out out/serving-check.json
  LightGBM models: uv run --with lightgbm serving_check.py ...

Exit code is 0 whenever the check ran (read "decision" in the JSON); 2 on unreadable input.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import pickle
import platform
import sys
import warnings
from pathlib import Path
from time import perf_counter

import joblib
import numpy as np
import pandas as pd
import sklearn

ROW_INDEX = "__row_index__"
FAMILY = {"numeric": "numeric", "bool": "bool", "datetime": "datetime", "categorical": "string", "text": "string"}


def die(msg: str):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(2)


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
    return o


# ------------------------------------------------------------------ loading

def load_model(path: str):
    t0 = perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            model = joblib.load(path)
        except ModuleNotFoundError as e:
            die(f"{e}. LightGBM models need: uv run --with lightgbm serving_check.py ...")
        except (OSError, ValueError, EOFError, pickle.UnpicklingError) as e:
            die(f"cannot load model {path}: {e}")
    # InconsistentVersionWarning here means the serving env runs a different sklearn than training: real skew.
    warns = [f"model load: {w.category.__name__}: {str(w.message)[:200]}" for w in caught]
    return model, (perf_counter() - t0) * 1000, warns


def read_csv(path: str, str_cols=()) -> pd.DataFrame:
    try:
        return pd.read_csv(path, dtype={c: str for c in str_cols if c and c != ROW_INDEX} or None)
    except (OSError, ValueError) as e:
        die(f"cannot read {path}: {e}")


def rebuild_rows(data: pd.DataFrame, key: str, ref_keys: pd.Series, label: str):
    """Raw input rows for each reference row_key, in reference order, with the label removed."""
    if key != ROW_INDEX and key not in data.columns:
        die(f"key column {key!r} not in data")
    keys = pd.Series(np.arange(len(data)).astype(str)) if key == ROW_INDEX else data[key].astype(str)
    if keys.duplicated().any():
        die(f"keys from {key!r} are not unique in the data")
    pos = ref_keys.map(pd.Series(np.arange(len(data)), index=keys.to_numpy()))
    found = pos.notna().to_numpy()
    # Serving never sees the label; dropping it proves the model doesn't need it.
    rows = data.iloc[pos[found].astype(int)].drop(columns=[label], errors="ignore").reset_index(drop=True)
    return rows, found


# ------------------------------------------------------------------ scoring & parity

def score(model, X: pd.DataFrame, task: str, pos_label) -> dict:
    if task == "regression":
        return {"y_pred": model.predict(X)}
    proba = model.predict_proba(X)
    classes = model.classes_
    if task == "binary":
        pos = int(np.flatnonzero(classes == (classes[-1] if pos_label is None else pos_label))[0])
        s = proba[:, pos]
        return {"y_score": s, "y_pred": classes[np.where(s >= 0.5, pos, 1 - pos)]}
    out = {f"score_{c}": proba[:, j] for j, c in enumerate(classes)}
    out["y_pred"] = classes[proba.argmax(axis=1)]
    return out


def abs_diff(ref: pd.Series, new) -> np.ndarray:
    a = pd.to_numeric(ref, errors="coerce").to_numpy(dtype=float)
    b = np.asarray(new, dtype=float)
    d = np.abs(a - b)
    d[np.isnan(a) & np.isnan(b)] = 0.0       # both missing counts as a match
    d[np.isnan(d)] = np.inf                  # one side missing is a mismatch
    return d


def check_parity(ref: pd.DataFrame, new: dict, task: str, atol: float) -> dict:
    if task == "regression":
        compared = ["y_pred"]
    elif task == "binary":
        compared = ["y_score"]
    else:
        compared = [c for c in ref.columns if c.startswith("score_")]
    missing = [c for c in compared if c not in new]
    if missing:
        return {"compared": compared, "error": f"model does not produce {missing} (class set changed?)",
                "parity_pass": False}
    diffs = np.column_stack([abs_diff(ref[c], new[c]) for c in compared]) if len(ref) else np.zeros((0, 1))
    row_max = diffs.max(axis=1) if len(ref) else np.array([])
    finite = row_max[np.isfinite(row_max)]
    result = {"compared": compared, "atol": atol,
              "max_abs_diff": float(finite.max()) if len(finite) else None,
              "n_mismatch": int((row_max > atol).sum())}
    if task != "regression":
        # Label flips are informational: a different decision threshold upstream also causes them.
        result["n_label_mismatch"] = int((ref["y_pred"].astype(str).to_numpy() != new["y_pred"].astype(str)).sum())
    result["parity_pass"] = result["n_mismatch"] == 0
    return result


# ------------------------------------------------------------------ contract (minimal, self-contained)

def infer_kind(s: pd.Series) -> str:
    """Same rules as data_contract.py: numeric | bool | datetime | categorical | text."""
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    nonnull = s.dropna()
    if len(nonnull) and all(isinstance(v, (bool, np.bool_)) for v in nonnull):
        return "bool"
    text = nonnull.astype(str)
    sample = text.head(2000)
    if len(sample) and sample.str.match(r"^\d{4}-\d{2}-\d{2}").mean() >= 0.95 and \
            pd.to_datetime(sample, errors="coerce", format="ISO8601").notna().mean() >= 0.95:
        return "datetime"
    if len(text) and text.str.len().mean() > 30 and text.nunique() > 0.5 * len(text):
        return "text"
    return "categorical"


def contract_check(contract: dict, rows: pd.DataFrame) -> dict:
    """Required feature columns present, dtype kinds unchanged, share of unseen categories."""
    violations = []
    for c in contract.get("columns", []):
        if c.get("role") != "feature":
            continue
        name = c["name"]
        if name not in rows.columns:
            violations.append({"column": name, "check": "missing_column", "severity": "blocker",
                               "detail": "feature column missing from serving input"})
            continue
        s = rows[name]
        if s.notna().any() and FAMILY[infer_kind(s)] != FAMILY.get(c["dtype_kind"], c["dtype_kind"]):
            violations.append({"column": name, "check": "dtype_kind", "severity": "blocker",
                               "detail": f"{c['dtype_kind']} in training, {infer_kind(s)} at serving"})
        elif c.get("allowed_values"):
            v = s.dropna().map(str)
            share = float((~v.isin(c["allowed_values"])).mean()) if len(v) else 0.0
            if share > 0:
                violations.append({"column": name, "check": "unseen_categories",
                                   "severity": "high" if share > 0.05 else "medium" if share > 0.01 else "low",
                                   "detail": f"{share:.1%} of values unseen in training"})
    return {"n_rows": len(rows), "violations": violations,
            "pass": not any(v["severity"] == "blocker" for v in violations)}


# ------------------------------------------------------------------ performance

def measure_latency(fn, X: pd.DataFrame, n: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    singles = [X.iloc[[i]] for i in rng.integers(0, len(X), size=n)]  # prebuilt 1-row frames
    for r in singles[:5]:
        fn(r)  # warm-up: first calls pay one-off costs (lazy imports, allocations)
    times = []
    for r in singles:
        t0 = perf_counter()
        fn(r)
        times.append((perf_counter() - t0) * 1000)
    p50, p95, p99 = np.percentile(times, [50, 95, 99])
    return {"n": n, "p50_ms": p50, "p95_ms": p95, "p99_ms": p99, "mean_ms": float(np.mean(times)),
            "max_ms": float(np.max(times)), "measures": "model call on a prebuilt 1-row DataFrame (no request parsing)"}


def measure_throughput(fn, X: pd.DataFrame, batch_size: int, seed: int) -> dict:
    batch = X.sample(n=batch_size, replace=len(X) < batch_size, random_state=seed)
    fn(batch)  # warm-up
    reps, elapsed = 0, 0.0
    while reps < 3 or (elapsed < 1.0 and reps < 50):
        t0 = perf_counter()
        fn(batch)
        elapsed += perf_counter() - t0
        reps += 1
    return {"rows_per_s": reps * len(batch) / elapsed, "batch_size": len(batch), "n_batches": reps,
            "batch_ms_mean": elapsed / reps * 1000}


def peak_rss_mb() -> float | None:
    try:
        import resource
    except ImportError:  # Windows
        return None
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / 2**20 if sys.platform == "darwin" else r / 1024  # macOS reports bytes, Linux KiB


# ------------------------------------------------------------------ main

def main(args) -> None:
    model, load_ms, warns = load_model(args.model)
    meta = getattr(model, "agentic_ml_", None) or {}

    if args.row_key_is_index:
        key = ROW_INDEX
    elif args.key_col:
        key = args.key_col
    elif meta.get("row_key"):
        key = meta["row_key"]
    else:
        die("cannot tell how rows are keyed: pass --key-col COL or --row-key-is-index")

    ref = read_csv(args.ref_pred, ["row_key"])
    if "row_key" not in ref.columns:
        die(f"{args.ref_pred} has no row_key column")
    if ref.empty:
        die(f"{args.ref_pred} has no rows")
    score_cols = [c for c in ref.columns if c.startswith("score_")]
    task = "binary" if "y_score" in ref.columns else "multiclass" if score_cols else "regression"
    if "y_pred" not in ref.columns:
        die(f"{args.ref_pred} has no y_pred column")
    if meta.get("task") and meta["task"] != task:
        warns.append(f"reference looks like {task} but the model was trained as {meta['task']}")

    data = read_csv(args.data, [key])
    rows, found = rebuild_rows(data, key, ref["row_key"], args.label_col)
    ref = ref[found].reset_index(drop=True)
    n_missing = int((~found).sum())
    if n_missing:
        warns.append(f"{n_missing} reference row_keys not found in {args.data}")

    feature_cols = list(getattr(model, "feature_names_in_", rows.columns))
    missing_feats = [c for c in feature_cols if c not in rows.columns]
    X = rows[[c for c in feature_cols if c in rows.columns]]

    contract = None
    if args.contract:
        try:
            contract = contract_check(json.loads(Path(args.contract).read_text()), rows)
        except (OSError, ValueError) as e:
            die(f"cannot read contract {args.contract}: {e}")

    fn = model.predict if task == "regression" else model.predict_proba
    latency = throughput = None
    if missing_feats:
        parity = {"error": f"serving input lacks model features {missing_feats}", "parity_pass": False}
    elif rows.empty:
        parity = {"error": "no reference rows could be rebuilt from the data", "parity_pass": False}
    else:
        try:
            parity = check_parity(ref, score(model, X, task, meta.get("pos_label")), task, args.atol)
            latency = measure_latency(fn, X, args.n_latency, args.seed)
            throughput = measure_throughput(fn, X, args.batch_size, args.seed)
        except Exception as e:  # noqa: BLE001 - any predict failure on serving input *is* the finding
            parity = {"error": f"predict failed on serving input: {type(e).__name__}: {e}", "parity_pass": False}
    parity.update({"task": task, "n_ref": int(len(found)), "n_scored": len(rows), "n_missing_keys": n_missing})
    if n_missing:
        parity["parity_pass"] = False
    if parity.get("n_label_mismatch"):
        warns.append(f"y_pred differs for {parity['n_label_mismatch']} rows (if scores match, check the threshold)")

    latency_ok = latency is not None and latency["p95_ms"] <= args.latency_budget_ms
    if latency and not latency_ok and not os.environ.get("OMP_NUM_THREADS"):
        warns.append("single-row latency over budget: tree models often pay thread-pool start-up per call; "
                     "re-measure with OMP_NUM_THREADS=1 before optimising the model")
    contract_high = bool(contract) and any(v["severity"] == "high" for v in contract["violations"])
    if not parity["parity_pass"] or (contract and not contract["pass"]):
        decision = "NO-GO"
    else:
        decision = "GO" if latency_ok and not contract_high else "CONDITIONAL"
    rss = peak_rss_mb()
    report = {
        "model": args.model, "data": args.data, "ref_pred": args.ref_pred, "row_key": key,
        "decision": decision, "parity": parity, "latency": latency, "throughput": throughput,
        "model_size_mb": os.path.getsize(args.model) / 2**20, "model_load_ms": load_ms,
        "peak_rss_mb": rss, "peak_rss_note": "whole process (Python + pandas + model); ru_maxrss, approximate",
        "contract_check": contract,
        "budget_pass": {"latency": latency_ok, "metric": "p95_ms", "budget_ms": args.latency_budget_ms},
        "environment": {"python": platform.python_version(), "sklearn": sklearn.__version__,
                        "pandas": pd.__version__, "numpy": np.__version__,
                        "omp_num_threads": os.environ.get("OMP_NUM_THREADS"), "cpu_count": os.cpu_count()},
        "warnings": warns,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(clean(report), indent=2) + "\n")

    p = parity
    ptxt = (f"parity {'PASS' if p['parity_pass'] else 'FAIL'}"
            + (f" (max_abs_diff={p['max_abs_diff']:.2e}, {p['n_mismatch']}/{p['n_scored']} > atol)"
               if p.get("max_abs_diff") is not None else f" ({p.get('error', '')})"))
    ltxt = f"p95 {latency['p95_ms']:.2f} ms (budget {args.latency_budget_ms:g})" if latency else "latency n/a"
    ttxt = f"{throughput['rows_per_s']:,.0f} rows/s" if throughput else "throughput n/a"
    print(f"serving_check: {decision} | {ptxt} | {ltxt} | {ttxt} | model {report['model_size_mb']:.2f} MB"
          + (f" | peak RSS {rss:.0f} MB" if rss else ""))
    if contract:
        sev = pd.Series([v["severity"] for v in contract["violations"]], dtype=object).value_counts().to_dict()
        print(f"  contract: {'PASS' if contract['pass'] else 'FAIL'} {sev or '(no violations)'}")
        for v in contract["violations"][:5]:
            print(f"    [{v['severity']}] {v['column']}: {v['check']} - {v['detail']}")
    for w in warns:
        print(f"  warning: {w}")
    print(f"  wrote {out}")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--model", required=True, help="fitted sklearn pipeline (model.joblib)")
    p.add_argument("--data", required=True, help="raw data CSV the reference rows came from")
    p.add_argument("--ref-pred", required=True, help="reference predictions CSV (row_key,y_true,y_score|score_*,y_pred)")
    p.add_argument("--label-col", required=True, help="dropped from the inputs before scoring")
    k = p.add_mutually_exclusive_group()
    k.add_argument("--key-col", default=None, help="column holding row_key (default: from model metadata)")
    k.add_argument("--row-key-is-index", action="store_true", help="row_key is the 0-based row index (__row_index__)")
    p.add_argument("--contract", default=None, help="data-contract.json for a schema check of the serving rows")
    p.add_argument("--latency-budget-ms", type=float, default=50.0, help="p95 single-row budget (default 50)")
    p.add_argument("--n-latency", type=int, default=200, help="single-row calls to time (default 200)")
    p.add_argument("--batch-size", type=int, default=1000, help="rows per batch for throughput (default 1000)")
    p.add_argument("--atol", type=float, default=1e-6, help="max allowed |reference - rescored| (default 1e-6)")
    p.add_argument("--seed", type=int, default=42, help="seed for picking latency/batch rows")
    p.add_argument("--out", required=True, help="output JSON path (serving-check.json)")
    a = p.parse_args(argv)
    if a.n_latency < 1 or a.batch_size < 1:
        p.error("--n-latency and --batch-size must be >= 1")
    return a


if __name__ == "__main__":
    main(parse_args())
