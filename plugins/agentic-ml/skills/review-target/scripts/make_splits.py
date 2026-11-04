#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "numpy>=1.24",
#   "pandas>=2.0",
#   "pyarrow>=14",  # parquet engine for --data *.parquet
# ]
# ///
"""Create the train/val/test split once and lock the test set.

Writes, under --out-dir:
  splits/split_assignments.csv  columns row_key,split  (split: train|val|test|excluded)
  splits/split-manifest.json    data hash, strategy, counts, label distribution, warnings,
                                and test_keys_sha256 (sha256 of the sorted test row_keys
                                joined by "\\n"), which eval_report.py checks later.

row_key is --id-col when it is unique and non-null, else the 0-based row index
(manifest row_key = "__row_index__"). Keys are written as strings (1.0 -> "1"); prediction
files must use the same values.

Strategies:
  random      shuffle rows
  stratified  shuffle within label classes (regression: within label deciles)
  group       no --group-col value lands in two splits; stratified by group label when feasible
  time        earliest rows train, then val, then test; each boundary moves to the nearest
              change in time so tied timestamps stay in one split; --gap drops rows in the
              window before val and before test (marked excluded)

Re-running with identical inputs reproduces the same split byte for byte. If --out-dir already
holds a different split (test or train/val), the script exits 3 unless --force.

Examples:
  uv run make_splits.py --data data.csv --label-col churned --strategy stratified --out-dir out
  uv run make_splits.py --data data.parquet --label-col y --strategy group --group-col user_id --out-dir out
  uv run make_splits.py --data data.csv --label-col is_fraud --strategy time \\
      --time-col ts --id-col txn_id --gap 7d --out-dir out
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import warnings as pywarnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROW_INDEX = "__row_index__"
MISSING = "__missing__"
SPLITS = ("train", "val", "test")
TRUE_TOKENS = {"true", "t", "yes", "y", "1", "positive", "pos"}
TIME_NAME_RE = re.compile(r"(date|time|_at$|_ts$|_dt$)", re.IGNORECASE)
ID_NAME_RE = re.compile(r"(^id$|_id$|^id_|uuid)", re.IGNORECASE)
MIN_POS, MIN_ROWS = 30, 100


def die(msg: str, code: int = 2) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def canon(v) -> str:
    """Stable string form of a cell: NaN -> __missing__, 1.0 -> '1', True -> 'True'."""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return MISSING
    if isinstance(v, (bool, np.bool_)):
        return str(bool(v))
    if isinstance(v, (float, np.floating)) and float(v).is_integer():
        return str(int(v))
    return str(v)


def canon_array(s: pd.Series) -> np.ndarray:
    return np.array([canon(v) for v in s], dtype=object)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def keys_sha256(keys) -> str:
    """sha256 of sorted string keys joined by newline (contract shared with eval_report.py)."""
    return hashlib.sha256("\n".join(sorted(map(str, keys))).encode()).hexdigest()


def load(path: Path) -> pd.DataFrame:
    name = path.name.lower()
    if name.endswith((".parquet", ".pq")):
        return pd.read_parquet(path)
    if name.endswith((".csv", ".csv.gz", ".tsv")):
        return pd.read_csv(path, sep="\t" if name.endswith(".tsv") else ",", low_memory=False)
    die(f"unsupported file type: {path} (expected .csv or .parquet)")


def to_datetime(s: pd.Series) -> pd.Series:
    """Parse to datetime quietly; fall back to UTC when offsets are mixed."""
    with pywarnings.catch_warnings():
        pywarnings.simplefilter("ignore")
        try:
            t = pd.to_datetime(s, errors="coerce")
        except (ValueError, TypeError):
            t = None
        if t is None or not pd.api.types.is_datetime64_any_dtype(t):
            t = pd.to_datetime(s, errors="coerce", utc=True)
    return t


def parse_time(s: pd.Series, col: str) -> pd.Series:
    """Datetime or numeric time column; exits if it does not parse."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return s
    if pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s):
        return s.astype(float)
    t = to_datetime(s)
    if s.notna().sum() and t.notna().sum() < 0.5 * s.notna().sum():
        die(f"--time-col {col!r} does not parse as datetime ({t.notna().sum()}/{s.notna().sum()} parsed)")
    return t


def detect_task(y: pd.Series, task: str) -> str:
    if task != "auto":
        return task
    if pd.api.types.is_bool_dtype(y) or not pd.api.types.is_numeric_dtype(y):
        return "classification"
    v = y.dropna()
    return "classification" if v.nunique() <= 10 and bool(np.all(np.mod(v, 1) == 0)) else "regression"


def positive_class(vc: pd.Series) -> str | None:
    """Positive class of a binary label: a truthy token ('True', 'yes', '1'), else the minority."""
    if len(vc) != 2:
        return None
    truthy = [c for c in vc.index if str(c).strip().lower() in TRUE_TOKENS]
    return truthy[0] if len(truthy) == 1 else str(vc.idxmin())


def time_like_cols(df: pd.DataFrame, exclude: set) -> list[str]:
    out = []
    for c in df.columns:
        s = df[c]
        if c in exclude:
            continue
        if pd.api.types.is_datetime64_any_dtype(s):
            out.append(c)
        elif TIME_NAME_RE.search(str(c)) and not pd.api.types.is_numeric_dtype(s):
            sample = s.dropna().astype(str).head(200)
            if len(sample) and to_datetime(sample).notna().mean() > 0.9:
                out.append(c)
    return out


def repeated_id_cols(df: pd.DataFrame, exclude: set) -> list[str]:
    """id-like columns with repeats that look like entities (>=5% unique), not categories."""
    out = []
    for c in df.columns:
        if c in exclude or not ID_NAME_RE.search(str(c)):
            continue
        nu, nn = df[c].nunique(), df[c].notna().sum()
        if nu < nn and nu >= 0.05 * len(df):
            out.append(c)
    return out


def assign_shuffled(idx: np.ndarray, rng, fv: float, ft: float, assign: np.ndarray) -> None:
    """Shuffle idx and give the first test_frac to test, the next val_frac to val, rest to train."""
    p = rng.permutation(idx)
    nt, nv = round(len(p) * ft), round(len(p) * fv)
    assign[p[:nt]], assign[p[nt:nt + nv]], assign[p[nt + nv:]] = "test", "val", "train"


def split_group(gkeys, strat, is_pos, rng, fv, ft, assign) -> dict:
    """Allocate whole groups by cumulative row share; stratify by group label when feasible."""
    df = pd.DataFrame({"g": gkeys, "s": strat if strat is not None else "all"})
    sizes = df.groupby("g", sort=True).size()
    glab = None
    if is_pos is not None:  # binary: a group is positive if any of its rows is
        glab = pd.Series(is_pos).groupby(gkeys).max().astype(int).astype(str).reindex(sizes.index)
    elif strat is not None:  # multiclass: modal label, ties broken by label name
        m = df.groupby(["g", "s"]).size().reset_index(name="k").sort_values(["g", "k", "s"], ascending=[True, False, True])
        glab = m.drop_duplicates("g").set_index("g")["s"].reindex(sizes.index)
    stratified = False
    if glab is not None:
        counts = glab.value_counts()
        min_frac = min(f for f in (fv, ft) if f > 0)
        stratified = len(counts) >= 2 and bool((counts * min_frac >= 1).all())
    if not stratified:
        glab = pd.Series("all", index=sizes.index)
    gsplit = {}
    for lab in sorted(glab.unique()):
        groups = rng.permutation(glab.index[glab == lab].to_numpy())
        sz = sizes.loc[groups].to_numpy(dtype=float)
        mid = (np.cumsum(sz) - sz / 2) / sz.sum()
        gsplit.update(zip(groups, np.where(mid < ft, "test", np.where(mid < ft + fv, "val", "train"))))
    assign[:] = pd.Series(gkeys).map(gsplit).to_numpy()
    return {"n_groups": len(sizes), "group_stratified": stratified}


def snap(st: pd.Series, c: int) -> int:
    """Move a boundary position to the nearer edge of its block of tied times (never to the end)."""
    if c >= len(st):
        return len(st)
    lo, hi = int(st.searchsorted(st.iloc[c], side="left")), int(st.searchsorted(st.iloc[c], side="right"))
    return hi if c - lo > hi - c and hi < len(st) else lo


def split_time(t: pd.Series, gap, fv: float, ft: float, assign: np.ndarray) -> dict:
    """Sort by time; split at the target positions, snapped so tied timestamps share a split."""
    valid = t.notna().to_numpy()
    st = t[valid].sort_values(kind="stable").reset_index(drop=True)
    m = len(st)
    nt, nv = round(m * ft), round(m * fv)
    c1, c2 = snap(st, m - nt - nv), snap(st, m - nt)
    if nv and c1 >= c2:  # snapping emptied val: put the tied block in val instead
        c1 = int(st.searchsorted(st.iloc[min(m - nt - nv, m - 1)], side="left"))
    t1 = st.iloc[c1] if c1 < m else None
    t2 = st.iloc[c2] if c2 < m else None
    is_test = (t >= t2).to_numpy() if t2 is not None else np.zeros(len(t), bool)
    is_val = ((t >= t1).to_numpy() & ~is_test) if t1 is not None else np.zeros(len(t), bool)
    is_train = valid & ~is_val & ~is_test
    drop_val = drop_test = np.zeros(len(t), bool)
    if gap is not None:
        if t1 is not None:
            drop_val = is_train & (t >= t1 - gap).to_numpy()
        if t2 is not None:
            drop_test = is_val & (t >= t2 - gap).to_numpy()
    assign[:] = "excluded"
    assign[is_train & ~drop_val] = "train"
    assign[is_val & ~drop_test] = "val"
    assign[is_test] = "test"
    return {
        "missing_time": int((~valid).sum()),
        "gap_dropped": {"before_val": int(drop_val.sum()), "before_test": int(drop_test.sum())},
        "boundaries": {"val_start": fmt_time(t1), "test_start": fmt_time(t2)},
    }


GAP_UNITS = {"w": "weeks", "week": "weeks", "weeks": "weeks", "d": "days", "day": "days", "days": "days",
             "h": "hours", "hr": "hours", "hour": "hours", "hours": "hours", "m": "minutes", "min": "minutes",
             "minute": "minutes", "minutes": "minutes", "s": "seconds", "sec": "seconds", "seconds": "seconds"}


def parse_gap(gap: str, numeric: bool):
    """'7d', '12h', '30min', '2w' -> Timedelta; a plain number for numeric time columns."""
    if numeric:
        try:
            return float(gap)
        except ValueError:
            die(f"--gap {gap!r} must be a number because --time-col is numeric")
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([a-zA-Z]+)\s*", gap)
    if not m or m.group(2).lower() not in GAP_UNITS:
        die(f"--gap {gap!r} is not a duration such as 7d, 12h, 30min or 2w")
    return pd.Timedelta(**{GAP_UNITS[m.group(2).lower()]: float(m.group(1))})


def fmt_time(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.isoformat() if hasattr(v, "isoformat") else float(v)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", required=True, type=Path, help="CSV or Parquet file")
    ap.add_argument("--label-col", required=True, help="target column")
    ap.add_argument("--strategy", required=True, choices=["random", "stratified", "group", "time"])
    ap.add_argument("--id-col", help="unique row id to use as row_key (default: 0-based row index)")
    ap.add_argument("--group-col", help="entity column (required for --strategy group)")
    ap.add_argument("--time-col", help="timestamp column (required for --strategy time)")
    ap.add_argument("--val-frac", type=float, default=0.15, help="default 0.15; 0 means no val split")
    ap.add_argument("--test-frac", type=float, default=0.15, help="default 0.15")
    ap.add_argument("--gap", help="time strategy: window dropped before val and before test, e.g. 7d, 12h; "
                    "a plain number for numeric time columns")
    ap.add_argument("--task", choices=["auto", "classification", "regression"], default="auto",
                    help="label type (auto: bool/string or <=10 integer values -> classification)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--force", action="store_true",
                    help="replace an existing, different split in --out-dir (record why; never compare across splits)")
    ap.add_argument("--out-dir", required=True, type=Path, help="writes <out-dir>/splits/")
    args = ap.parse_args(argv)

    fv, ft = args.val_frac, args.test_frac
    if not (0 < ft < 1 and 0 <= fv < 1 and fv + ft < 1):
        die("need 0 < --test-frac < 1, 0 <= --val-frac < 1 and val + test < 1")
    if args.strategy == "group" and not args.group_col:
        die("--strategy group requires --group-col")
    if args.strategy == "time" and not args.time_col:
        die("--strategy time requires --time-col")
    if args.gap and args.strategy != "time":
        die("--gap only applies to --strategy time")
    if not args.data.is_file():
        die(f"data file not found: {args.data}")

    df = load(args.data)
    n = len(df)
    if n == 0:
        die(f"{args.data} has no rows")
    for flag, col in (("--label-col", args.label_col), ("--id-col", args.id_col),
                      ("--group-col", args.group_col), ("--time-col", args.time_col)):
        if col and col not in df.columns:
            die(f"{flag} {col!r} not in columns: {list(df.columns)[:30]}")
    warns: list[str] = []

    # Row key
    keys, row_key, id_unique = np.arange(n).astype(str).astype(object), ROW_INDEX, False
    if args.id_col:
        ids = canon_array(df[args.id_col])
        n_null, n_dup = int((ids == MISSING).sum()), int(pd.Series(ids).duplicated().sum())
        if n_null or n_dup:
            warns.append(f"--id-col {args.id_col!r} is not a unique key ({n_dup} duplicates, {n_null} nulls); "
                         f"using the 0-based row index as row_key")
        else:
            keys, row_key, id_unique = ids, args.id_col, True

    # Label
    y = df[args.label_col]
    task = detect_task(y, args.task)
    labels = canon_array(y)
    n_missing_label = int((labels == MISSING).sum())
    if n_missing_label:
        warns.append(f"{n_missing_label} rows have a missing label; they are still assigned to splits")
    pos, is_pos, ynum = None, None, None
    if task == "classification":
        vc = pd.Series(labels[labels != MISSING]).value_counts()
        pos = positive_class(vc)
        is_pos = (labels == pos).astype(int) if pos is not None else None
        strat = labels
    else:
        ynum = pd.to_numeric(y, errors="coerce")
        if ynum.notna().sum() == 0:
            die(f"--label-col {args.label_col!r} is not numeric; use --task classification")
        bins = pd.qcut(ynum, 10, labels=False, duplicates="drop")
        strat = canon_array(bins)

    # Split
    rng = np.random.default_rng(args.seed)
    assign = np.full(n, "train", dtype=object)
    extra: dict = {}
    t = None
    if args.strategy == "random":
        assign_shuffled(np.arange(n), rng, fv, ft, assign)
    elif args.strategy == "stratified":
        for lab in sorted(set(strat)):
            assign_shuffled(np.flatnonzero(strat == lab), rng, fv, ft, assign)
    elif args.strategy == "group":
        g = canon_array(df[args.group_col])
        miss = g == MISSING
        if miss.any():
            warns.append(f"{int(miss.sum())} rows have a missing --group-col; each is treated as its own group")
            g[miss] = [f"{MISSING}{i}" for i in np.flatnonzero(miss)]
        extra = split_group(g, strat if task == "classification" else None, is_pos, rng, fv, ft, assign)
        if not extra["group_stratified"] and task == "classification":
            warns.append("too few groups per label class to stratify; groups were shuffled without stratification")
    else:
        t = parse_time(df[args.time_col], args.time_col)
        gap = parse_gap(args.gap, numeric=pd.api.types.is_float_dtype(t)) if args.gap else None
        extra = split_time(t, gap, fv, ft, assign)
        if extra["missing_time"]:
            warns.append(f"{extra['missing_time']} rows have a missing/unparseable time; marked excluded")
        if fv > 0 and extra["boundaries"]["val_start"] == extra["boundaries"]["test_start"]:
            warns.append("val is empty: the val and test boundaries fall on the same timestamp")

    counts = {s: int((assign == s).sum()) for s in (*SPLITS, "excluded")}

    # Label distribution per split
    dist = {}
    for s in SPLITS:
        m = assign == s
        if task == "classification":
            vc = pd.Series(labels[m]).value_counts().sort_index()
            d = {"counts": {str(k): int(v) for k, v in vc.items()}}
            if pos is not None:
                nn = int((labels[m] != MISSING).sum())
                d["positive_rate"] = round(float(is_pos[m].sum()) / nn, 6) if nn else None
            dist[s] = d
        else:
            v = ynum[m]
            dist[s] = {"mean": None if v.isna().all() else float(v.mean()),
                       "std": None if v.notna().sum() < 2 else float(v.std())}

    # Group overlap between splits
    overlap = None
    ocol = args.group_col or args.id_col
    if ocol:
        gv = canon_array(df[ocol])
        sets = {s: set(gv[(assign == s) & (gv != MISSING)]) for s in SPLITS}
        overlap = {"column": ocol, "train_val": len(sets["train"] & sets["val"]),
                   "train_test": len(sets["train"] & sets["test"]), "val_test": len(sets["val"] & sets["test"])}

    # Sample-size warnings
    for s in ("val", "test"):
        if s == "val" and fv == 0:
            continue
        if counts[s] < MIN_ROWS:
            warns.append(f"{s} split has {counts[s]} rows (< {MIN_ROWS}); metrics will be noisy")
        if task == "classification":
            m = assign == s
            if pos is not None:
                npos = int(is_pos[m].sum())
                if npos < MIN_POS:
                    warns.append(f"{s} split has {npos} positives (< {MIN_POS}); intervals will be too wide to decide on")
            else:
                cls = [c for c in pd.Series(labels[labels != MISSING]).unique()]
                small = {c: int((labels[m] == c).sum()) for c in cls}
                small = {c: k for c, k in small.items() if k < MIN_POS}
                if small:
                    warns.append(f"{s} split has classes with < {MIN_POS} rows: {dict(list(small.items())[:5])}")

    # Strategy-fit warnings
    if args.strategy in ("random", "stratified"):
        tcols = [args.time_col] if args.time_col else time_like_cols(df, {args.label_col})
        if tcols:
            warns.append(f"{args.strategy} split on data with time column(s) {tcols}: later rows can train a model "
                         f"scored on earlier ones; consider --strategy time --time-col {tcols[0]}")
        rep = [c for c in (args.group_col, None if id_unique else args.id_col) if c]
        rep += [c for c in repeated_id_cols(df, {args.label_col, args.id_col, args.group_col}) if c not in rep]
        if rep:
            warns.append(f"{args.strategy} split on data with repeated id(s) {rep}: the same entity can land in "
                         f"train and test; consider --strategy group --group-col {rep[0]}")
    if overlap and args.strategy == "group" and (overlap["train_val"] or overlap["train_test"] or overlap["val_test"]):
        warns.append(f"group overlap between splits: {overlap}")

    test_hash = keys_sha256(keys[assign == "test"])
    out = args.out_dir / "splits"
    man_path, asg_path = out / "split-manifest.json", out / "split_assignments.csv"
    asg_csv = pd.DataFrame({"row_key": keys, "split": assign}).to_csv(index=False, lineterminator="\n")
    if (man_path.exists() or asg_path.exists()) and not args.force:
        try:
            old_test = json.loads(man_path.read_text()).get("test_keys_sha256")
            same = old_test == test_hash and asg_path.read_text() == asg_csv
        except (OSError, ValueError):
            old_test, same = None, False
        if not same:
            what = "test set" if old_test != test_hash else "train/val assignment"
            die(f"{out} already holds a split with a different {what}; splits are locked. Pass --force only if the "
                f"old split is invalid (record why), and never compare results across splits.", 3)

    manifest = {
        "data_path": str(args.data.resolve()),
        "data_sha256": sha256_file(args.data),
        "n_rows": n,
        "row_key": row_key,
        "strategy": args.strategy,
        "task": task,
        "label_col": args.label_col,
        "positive_class": pos,
        "id_col": args.id_col,
        "group_col": args.group_col,
        "time_col": args.time_col,
        "seed": args.seed,
        "fractions": {"train": round(1 - fv - ft, 6), "val": fv, "test": ft},
        "gap": args.gap,
        "counts": counts,
        "label_distribution": dist,
        "time_ranges": None,
        "group_overlap": overlap,
        "test_keys_sha256": test_hash,
        "assignments_path": "splits/split_assignments.csv",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "warnings": warns,
        **extra,
    }
    if t is not None:
        manifest["time_ranges"] = {s: [fmt_time(t[assign == s].min()), fmt_time(t[assign == s].max())]
                                   if counts[s] else None for s in SPLITS}

    out.mkdir(parents=True, exist_ok=True)
    asg_path.write_text(asg_csv)
    man_path.write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"{args.strategy} split ({task}, seed {args.seed}) of {n} rows -> {out}/")
    print("  " + " | ".join(f"{s} {counts[s]}" for s in (*SPLITS, "excluded")))
    if pos is not None:
        print(f"  positives ({pos}): " + " | ".join(f"{s} {int(is_pos[assign == s].sum())}" for s in SPLITS))
    if manifest["time_ranges"]:
        print("  time: " + " | ".join(f"{s} {r[0]}..{r[1]}" for s, r in manifest["time_ranges"].items() if r))
    if overlap:
        print(f"  {ocol} overlap: train/val {overlap['train_val']}, train/test {overlap['train_test']}, "
              f"val/test {overlap['val_test']}")
    print(f"  row_key: {row_key}   test_keys_sha256: {test_hash[:16]}...")
    for w in warns:
        print(f"  WARNING: {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
