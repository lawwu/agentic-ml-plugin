#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "numpy>=1.24",
#   "pandas>=2.2",
# ]
# ///
"""
data_contract.py: a data contract and drift baseline learned from training rows (check-dataset-quality skill).

  build     Write data-contract.json (columns, dtype kinds, null budgets, ranges, allowed levels, roles)
            and training-profile.json (decile bins / top-50 level frequencies used for PSI drift).
  validate  Check new data (a scoring batch, a fresh extract) against the contract and profile.
            Exits 0 even when violations are found; exits 2 only on unreadable input.

Examples:
  uv run data_contract.py build --data data.csv --splits out/splits --split train \\
      --label-col churned --out-dir out/contract
  uv run data_contract.py validate --contract out/contract/data-contract.json \\
      --profile out/contract/training-profile.json --data new_batch.csv --out out/contract/validation.json

Why train rows only: the contract and drift baseline describe what the model learned from.
Building them from val/test rows would quietly tune the reference to the evaluation data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROW_INDEX = "__row_index__"
MAX_LEVELS = 50          # categorical columns with more levels get no allowed_values list
PSI_EPS = 1e-4           # floor for empty bins so log() stays finite
FAMILY = {"numeric": "numeric", "bool": "bool", "datetime": "datetime", "categorical": "string", "text": "string"}
SEVERITIES = ["blocker", "high", "medium", "low"]


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
        return float(o) if math.isfinite(o) else None
    return o


def write_json(path: Path, obj) -> None:
    path.write_text(json.dumps(clean(obj), indent=2) + "\n")


def read_json(path: str) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        die(f"cannot read {path}: {e}")


def read_csv(path: str, str_cols=()) -> pd.DataFrame:
    # ID-like columns are read as text so "007" and 7 compare consistently across files.
    try:
        return pd.read_csv(path, dtype={c: str for c in str_cols if c and c != ROW_INDEX} or None)
    except (OSError, ValueError) as e:
        die(f"cannot read {path}: {e}")


# ------------------------------------------------------------------ column typing

def infer_kind(s: pd.Series) -> str:
    """numeric | bool | datetime | categorical | text."""
    if pd.api.types.is_bool_dtype(s):
        return "bool"
    if pd.api.types.is_numeric_dtype(s):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(s):
        return "datetime"
    nonnull = s.dropna()
    if len(nonnull) and all(isinstance(v, (bool, np.bool_)) for v in nonnull):
        return "bool"  # pandas reads a True/False column with blanks as object
    text = nonnull.astype(str)
    sample = text.head(2000)
    if len(sample) and sample.str.match(r"^\d{4}-\d{2}-\d{2}").mean() >= 0.95 and \
            pd.to_datetime(sample, errors="coerce", format="ISO8601").notna().mean() >= 0.95:
        return "datetime"
    if len(text) and text.str.len().mean() > 30 and text.nunique() > 0.5 * len(text):
        return "text"
    return "categorical"


def as_levels(s: pd.Series) -> pd.Series:
    """Canonical string form of category levels (True -> "True"), NaN dropped."""
    return s.dropna().map(str)


def numeric_proportions(s: pd.Series, edges) -> np.ndarray:
    """Share of rows per bin (-inf,e0], (e0,e1], ..., (e_last,inf), plus a final 'missing' bin."""
    x = pd.to_numeric(s, errors="coerce").to_numpy(dtype=float)
    missing = np.isnan(x)
    idx = np.searchsorted(np.asarray(edges, dtype=float), x[~missing], side="left")
    counts = np.bincount(idx, minlength=len(edges) + 1)
    return np.append(counts, missing.sum()) / max(len(x), 1)


def level_proportions(s: pd.Series, levels) -> dict:
    v = as_levels(s)
    n = max(len(s), 1)
    known = v[v.isin(levels)].value_counts()
    props = {lv: known.get(lv, 0) / n for lv in levels}
    props["__other__"] = (len(v) - known.sum()) / n
    props["__missing__"] = s.isna().sum() / n
    return props


def profile_column(s: pd.Series, kind: str) -> dict | None:
    if kind == "numeric":
        x = pd.to_numeric(s, errors="coerce").dropna()
        # Decile cut points; np.unique merges ties so discrete columns get fewer, wider bins.
        edges = np.unique(np.quantile(x, np.linspace(0.1, 0.9, 9))) if len(x) else np.array([])
        return {"kind": "numeric", "bin_edges": edges, "proportions": numeric_proportions(s, edges)}
    if kind in ("categorical", "bool"):
        counts = as_levels(s).value_counts().sort_index().sort_values(ascending=False, kind="stable")
        return {"kind": "categorical", "frequencies": level_proportions(s, counts.index[:MAX_LEVELS].tolist())}
    return None  # datetime/text: PSI on raw timestamps or free text is not meaningful


def psi(expected, actual) -> float:
    e = np.maximum(np.asarray(expected, dtype=float), PSI_EPS)
    a = np.maximum(np.asarray(actual, dtype=float), PSI_EPS)
    return float(np.sum((a - e) * np.log(a / e)))


def psi_level(v: float) -> str:
    return "stable" if v < 0.1 else "moderate" if v <= 0.25 else "major"


# ------------------------------------------------------------------ build

def load_training_rows(args):
    """All rows, or only rows of --split when --splits is given."""
    manifest = {}
    if args.splits:
        d = Path(args.splits)
        d = d.parent if d.is_file() else d
        manifest = read_json(str(d / "split-manifest.json"))
        try:
            assign = pd.read_csv(d / "split_assignments.csv", dtype=str, keep_default_na=False)
        except (OSError, ValueError) as e:
            die(f"cannot read {d / 'split_assignments.csv'}: {e}")
        if assign["row_key"].duplicated().any():
            die("split_assignments.csv has duplicate row_key values")
    id_cols = args.id_cols + [manifest.get("row_key"), manifest.get("group_col")]
    df = read_csv(args.data, id_cols)
    if args.splits:
        key = manifest.get("row_key") or ROW_INDEX
        if key != ROW_INDEX and key not in df.columns:
            die(f"row_key column {key!r} not in data")
        keys = pd.Series(np.arange(len(df)).astype(str)) if key == ROW_INDEX else df[key].astype(str)
        split = keys.map(assign.set_index("row_key")["split"]).to_numpy()
        df = df.loc[split == args.split].reset_index(drop=True)
    return df, manifest


def assign_roles(columns, args, manifest) -> dict:
    roles = {c: "feature" for c in columns}
    for c in args.exclude_cols + [manifest.get("time_col")]:
        if c in roles:
            roles[c] = "excluded"
    for c in args.id_cols + [manifest.get("row_key"), manifest.get("group_col")]:
        if c in roles:
            roles[c] = "id"
    if args.label_col in roles:
        roles[args.label_col] = "label"
    return roles


def cmd_build(args) -> None:
    df, manifest = load_training_rows(args)
    if df.empty:
        die("no rows to build a contract from (empty file or empty split)")
    if args.label_col not in df.columns:
        die(f"label column {args.label_col!r} not in data")
    roles = assign_roles(df.columns, args, manifest)
    columns, profiles = [], {}
    for name in df.columns:
        s = df[name]
        kind = infer_kind(s)
        null_rate = float(s.isna().mean())
        n_unique = int(s.nunique())
        col = {
            "name": name, "role": roles[name], "dtype_kind": kind,
            "nullable": null_rate > 0, "null_rate": null_rate,
            # Small tolerance so normal batch-to-batch noise in missingness doesn't fire alerts.
            "max_null_rate": min(1.0, null_rate + args.null_tolerance),
            "min": None, "max": None, "allowed_values": None, "n_unique": n_unique,
        }
        if kind == "numeric":
            x = pd.to_numeric(s, errors="coerce")
            col["min"], col["max"] = x.min(), x.max()
        if kind in ("categorical", "bool") and n_unique <= MAX_LEVELS:
            col["allowed_values"] = sorted(as_levels(s).unique().tolist())
        columns.append(col)
        if roles[name] in ("feature", "label") and (p := profile_column(s, kind)):
            profiles[name] = p

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    source = {"data": args.data, "data_sha256": hashlib.sha256(Path(args.data).read_bytes()).hexdigest(),
              "splits": args.splits, "split": args.split if args.splits else None, "n_rows": len(df)}
    write_json(out / "data-contract.json", {"version": 1, "source": source, "label_col": args.label_col,
                                            "null_tolerance": args.null_tolerance, "columns": columns})
    write_json(out / "training-profile.json", {
        "version": 1, "source": source,
        "bins": "numeric: proportions over (-inf,e0],(e0,e1],...,(e_last,inf) then a missing bin; "
                "categorical: top-50 levels + __other__ + __missing__",
        "columns": profiles})
    by_role = pd.Series(roles).value_counts().to_dict()
    print(f"data_contract build: {len(df)} rows, {len(columns)} columns {by_role}, {len(profiles)} profiled -> {out}")


# ------------------------------------------------------------------ validate

def share_severity(share: float, important: bool) -> str:
    if not important:
        return "low"
    return "high" if share > 0.05 else "medium" if share > 0.01 else "low"


def validate(contract: dict, profile: dict, df: pd.DataFrame) -> dict:
    violations, drift = [], []

    def add(column, check, severity, detail):
        violations.append({"column": column, "check": check, "severity": severity, "detail": detail})

    n = len(df)
    if n == 0:
        add(None, "empty_input", "blocker", "no rows to validate")
    spec = {c["name"]: c for c in contract["columns"]}
    for name, c in spec.items():
        role = c["role"]
        important = role in ("feature", "label")
        if name not in df.columns:
            if role != "label":  # labels are normally absent from inference data
                add(name, "missing_column", {"feature": "blocker", "id": "medium"}.get(role, "low"),
                    f"{role} column missing")
            continue
        if n == 0:
            continue
        s = df[name]
        null_rate = float(s.isna().mean())
        if null_rate > c["max_null_rate"]:
            add(name, "null_rate", "high" if important else "medium",
                f"null rate {null_rate:.3f} > max {c['max_null_rate']:.3f} (train {c['null_rate']:.3f})")
        elif null_rate > 0 and not c["nullable"]:
            add(name, "unexpected_nulls", "low", f"null rate {null_rate:.3f}; column had no nulls in training")
        if s.notna().any():
            kind = infer_kind(s)
            if FAMILY[kind] != FAMILY[c["dtype_kind"]]:
                add(name, "dtype_kind", "blocker" if important else "medium", f"{c['dtype_kind']} in training, {kind} now")
                continue  # range, level and drift checks are meaningless on the wrong type
        if c["dtype_kind"] == "numeric" and c["min"] is not None:
            x = pd.to_numeric(s, errors="coerce").dropna()
            share = float(((x < c["min"]) | (x > c["max"])).mean()) if len(x) else 0.0
            if share > 0:
                add(name, "out_of_range", share_severity(share, important),
                    f"{share:.1%} of values outside training range [{c['min']}, {c['max']}]")
        if c["allowed_values"] is not None:
            v = as_levels(s)
            unseen = v[~v.isin(c["allowed_values"])]
            share = len(unseen) / len(v) if len(v) else 0.0
            if share > 0:
                add(name, "unseen_categories", share_severity(share, important),
                    f"{share:.1%} of values unseen in training, e.g. {sorted(unseen.unique().tolist())[:5]}")
        p = profile.get("columns", {}).get(name)
        if p:
            if p["kind"] == "numeric":
                expected, actual = p["proportions"], numeric_proportions(s, p["bin_edges"])
            else:
                levels = [k for k in p["frequencies"] if k not in ("__other__", "__missing__")]
                expected = list(p["frequencies"].values())
                actual = list(level_proportions(s, levels).values())
            value = psi(expected, actual)
            drift.append({"column": name, "role": role, "psi": round(value, 4), "level": psi_level(value)})
    for name in df.columns:
        if name not in spec:
            add(name, "extra_column", "low", "not in the contract (ignored by the model)")

    violations.sort(key=lambda v: SEVERITIES.index(v["severity"]))
    drift.sort(key=lambda d: -d["psi"])
    by_sev = {s: sum(v["severity"] == s for v in violations) for s in SEVERITIES}
    by_level = {lv: sum(d["level"] == lv for d in drift) for lv in ("stable", "moderate", "major")}
    decision = "NO-GO" if by_sev["blocker"] else "CONDITIONAL" if by_sev["high"] or by_level["major"] else "GO"
    return {"violations": violations, "drift": drift,
            "summary": {"n_rows": n, "n_columns": len(df.columns), "violations_by_severity": by_sev,
                        "drift_by_level": by_level, "decision": decision}}


def cmd_validate(args) -> None:
    contract, profile = read_json(args.contract), read_json(args.profile)
    if "columns" not in contract:
        die(f"{args.contract} is not a data contract (no 'columns')")
    id_cols = [c["name"] for c in contract["columns"] if c["role"] == "id"]
    result = validate(contract, profile, read_csv(args.data, id_cols))
    result["data"] = args.data
    sm = result["summary"]
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        write_json(Path(args.out), result)
    else:
        print(json.dumps(clean(result), indent=2))
    print(f"data_contract validate: {sm['decision']} | {sm['n_rows']} rows | violations {sm['violations_by_severity']} "
          f"| drift {sm['drift_by_level']}", file=sys.stderr if not args.out else sys.stdout)
    for v in result["violations"][:8]:
        print(f"  [{v['severity']}] {v['column']}: {v['check']} - {v['detail']}",
              file=sys.stderr if not args.out else sys.stdout)


def parse_args(argv=None):
    cols = lambda s: [c for c in s.split(",") if c]  # noqa: E731
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", help="build data-contract.json + training-profile.json from training rows")
    b.add_argument("--data", required=True, help="CSV file")
    b.add_argument("--splits", default=None, help="dir with split_assignments.csv + split-manifest.json (recommended)")
    b.add_argument("--split", default="train", help="which split to learn from (default: train)")
    b.add_argument("--label-col", required=True)
    b.add_argument("--exclude-cols", type=cols, default=[], help="comma-separated columns with role 'excluded'")
    b.add_argument("--id-cols", type=cols, default=[], help="comma-separated identifier columns (role 'id')")
    b.add_argument("--null-tolerance", type=float, default=0.02, help="added to the observed null rate (default 0.02)")
    b.add_argument("--out-dir", required=True)
    b.set_defaults(func=cmd_build)

    v = sub.add_parser("validate", help="check new data against a contract + PSI drift vs the profile")
    v.add_argument("--contract", required=True)
    v.add_argument("--profile", required=True)
    v.add_argument("--data", required=True, help="new CSV to validate")
    v.add_argument("--out", default=None, help="write the JSON report here (default: print to stdout)")
    v.set_defaults(func=cmd_validate)
    return p.parse_args(argv)


if __name__ == "__main__":
    a = parse_args()
    a.func(a)
