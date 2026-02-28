# Format Loading Reference

Reference for the `dataset-audit` skill. Efficient loading patterns per file format with sampling support.

---

## CSV

**Library**: `pandas` (default) or `polars` (faster for large files)

```python
import pandas as pd

# Full load (small files)
df = pd.read_csv(path)

# Sampled load (large files) — row-level sampling
df = pd.read_csv(path, nrows=sample_n)  # First N rows

# Random sample (requires two passes, use for audit)
total = sum(1 for _ in open(path)) - 1  # count rows
skip = sorted(random.sample(range(1, total + 1), total - sample_n))
df = pd.read_csv(path, skiprows=skip)

# Handle encoding issues
df = pd.read_csv(path, encoding="utf-8", encoding_errors="replace")
# If mojibake: try encoding="latin-1" or "cp1252"

# Detect delimiter automatically
import csv
with open(path, newline="") as f:
    dialect = csv.Sniffer().sniff(f.read(4096))
df = pd.read_csv(path, sep=dialect.delimiter)
```

**Pitfalls**:
- Default `dtype` inference can silently coerce types (e.g., `"NA"` → NaN, `"1e5"` → float)
- Use `dtype=str` for initial load if doing type auditing
- Leading/trailing whitespace in column names: use `df.columns = df.columns.str.strip()`

---

## Parquet

**Library**: `pandas` + `pyarrow` (or `fastparquet`)

```python
import pandas as pd

# Full load
df = pd.read_parquet(path)

# Column subset (efficient for wide tables)
df = pd.read_parquet(path, columns=["text", "label", "id"])

# Sampled load (read all, then sample — Parquet doesn't support row-level skip efficiently)
df = pd.read_parquet(path).sample(n=min(sample_n, len(df)), random_state=42)

# Multi-file Parquet directory
import glob
dfs = [pd.read_parquet(f) for f in sorted(glob.glob(f"{path}/*.parquet"))]
df = pd.concat(dfs, ignore_index=True)

# Validate without full load (schema only)
import pyarrow.parquet as pq
schema = pq.read_schema(path)
print(schema)
metadata = pq.read_metadata(path)
print(f"rows={metadata.num_rows}, row_groups={metadata.num_row_groups}")
```

**Pitfalls**:
- Parquet preserves dtypes precisely — check for `int32` vs `int64`, `float32` vs `float64`
- Corrupt row groups cause `ArrowInvalid` — test with `pq.read_metadata` first
- Snappy/gzip/zstd compressed: transparent to pandas, but affects I/O speed

---

## JSONL (JSON Lines)

**Library**: `pandas` + `json` or `datasets`

```python
import pandas as pd

# Full load
df = pd.read_json(path, lines=True)

# Sampled load (streaming, memory-efficient)
import json

rows = []
with open(path) as f:
    for i, line in enumerate(f):
        if i >= sample_n:
            break
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            print(f"[WARN] Parse error on line {i}: {e}")
df = pd.DataFrame(rows)

# Random sample from JSONL (two-pass)
import random
with open(path) as f:
    all_lines = f.readlines()
sampled = random.sample(all_lines, min(sample_n, len(all_lines)))
rows = [json.loads(l) for l in sampled if l.strip()]
df = pd.DataFrame(rows)
```

**Pitfalls**:
- Mixed schema across lines → `pd.read_json(lines=True)` will produce NaN for missing keys
- Deeply nested JSON → flatten with `pd.json_normalize()`
- Unicode escapes in text fields → validate with `ftfy.fix_text()` if expecting clean text

---

## HuggingFace Hub Datasets

**Library**: `datasets`

```python
from datasets import load_dataset

# Load specific split
ds = load_dataset("owner/name", split="train")

# Sampled load (streaming mode — no full download)
ds = load_dataset("owner/name", split="train", streaming=True)
sample = list(ds.take(sample_n))
df = pd.DataFrame(sample)

# Load with specific config/subset
ds = load_dataset("owner/name", "subset_name", split="train")

# Convert to pandas
df = ds.to_pandas()

# Access multiple splits
ds = load_dataset("owner/name")  # Returns DatasetDict
splits = {name: split.to_pandas() for name, split in ds.items()}

# Schema inspection without loading
from datasets import load_dataset_builder
builder = load_dataset_builder("owner/name")
print(builder.info.features)
```

**Pitfalls**:
- HF datasets cache at `~/.cache/huggingface/datasets/` — disk usage can be large
- `streaming=True` does not support `.shuffle()` efficiently
- Some datasets require `trust_remote_code=True` → confirm source before using
- Arrow format preserves exact dtypes; use `ds.features` to inspect before loading

---

## Image Directories

**Expected structure**: `root/class_name/image.jpg` (PyTorch `ImageFolder` convention)

```python
import os
from pathlib import Path
from PIL import Image
import pandas as pd

root = Path(path)

# Discover all images and their class labels
records = []
for class_dir in sorted(root.iterdir()):
    if not class_dir.is_dir():
        continue
    for img_path in class_dir.rglob("*"):
        if img_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff"}:
            records.append({"path": str(img_path), "label": class_dir.name})

df = pd.DataFrame(records)

# Sample and validate
sample = df.sample(n=min(sample_n, len(df)), random_state=42)
errors = []
widths, heights = [], []
for _, row in sample.iterrows():
    try:
        img = Image.open(row["path"])
        img.verify()
        widths.append(img.width)
        heights.append(img.height)
    except Exception as e:
        errors.append({"path": row["path"], "error": str(e)})
```

**Pitfalls**:
- `img.verify()` closes the file — reopen if you need pixel data after verification
- Truncated images pass `verify()` but fail on pixel access — use `img.load()` instead
- Mixed image modes (RGB, RGBA, L, P) → normalize with `img.convert("RGB")`
- Symlinks in the directory can cause double-counting

---

## Database Tables

**Library**: `SQLAlchemy` + `pandas` for local/cloud SQL; dialect-specific clients for BigQuery/Snowflake.

### Connection strings (`--db-url`)

| Database | DSN format |
|---|---|
| PostgreSQL | `postgresql://user:pass@host:5432/dbname` |
| MySQL / MariaDB | `mysql+pymysql://user:pass@host/dbname` |
| SQLite | `sqlite:///absolute/path/to/db.sqlite` |
| BigQuery | `bigquery://project/dataset` (uses ADC) |
| Snowflake | `snowflake://user:pass@account/database/schema` |
| DuckDB | `duckdb:///path/to/file.duckdb` |

### Schema inspection (never load all rows first)

```python
from sqlalchemy import create_engine, inspect, text

engine = create_engine(db_url)
insp = inspect(engine)

# List tables in schema
tables = insp.get_table_names(schema=schema)

# Column names and types
cols = insp.get_columns(table_name, schema=schema)
for c in cols:
    print(c["name"], c["type"])

# Row count (cheap)
with engine.connect() as conn:
    count = conn.execute(text(f"SELECT COUNT(*) FROM {schema}.{table}")).scalar()
```

### Sampling strategies by dialect

Always push sampling to the DB rather than pulling all rows:

```python
import pandas as pd
from sqlalchemy import create_engine, text

engine = create_engine(db_url)

# PostgreSQL / MySQL / SQLite — LIMIT with random ordering
query = f"SELECT * FROM {table} ORDER BY RANDOM() LIMIT {sample_n}"

# PostgreSQL — TABLESAMPLE (faster for large tables, approximate)
query = f"SELECT * FROM {table} TABLESAMPLE BERNOULLI(1)"  # ~1% sample

# BigQuery — TABLESAMPLE
query = f"SELECT * FROM `{project}.{dataset}.{table}` TABLESAMPLE SYSTEM (1 PERCENT)"

# Snowflake — SAMPLE
query = f"SELECT * FROM {table} SAMPLE ({sample_pct} PERCENT)"

df = pd.read_sql(text(query), engine)
```

### Push-down profiling (preferred for large tables)

Compute statistics in-database rather than in Python to avoid transferring millions of rows:

```python
from sqlalchemy import create_engine, text

engine = create_engine(db_url)

# Per-column null rates (single scan)
null_query = """
SELECT
  COUNT(*) AS total_rows,
  {null_exprs}
FROM {schema}.{table}
""".format(
    null_exprs=",\n  ".join(
        f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) AS {col}_nulls"
        for col in columns
    ),
    schema=schema,
    table=table,
)

# Approximate distinct counts (PostgreSQL)
distinct_query = f"SELECT COUNT(DISTINCT {col}) FROM {schema}.{table}"
# For BigQuery use APPROX_COUNT_DISTINCT({col})
# For Snowflake use APPROX_COUNT_DISTINCT({col})

# Label distribution
label_query = f"""
SELECT {label_col}, COUNT(*) AS cnt
FROM {schema}.{table}
GROUP BY {label_col}
ORDER BY cnt DESC
"""

with engine.connect() as conn:
    null_stats = pd.read_sql(text(null_query), conn)
    label_dist = pd.read_sql(text(label_query), conn)
```

### Cross-table leakage check

When train and test are in separate tables (common in prod DBs):

```python
leakage_query = f"""
SELECT COUNT(*) AS overlap_count
FROM {train_table} t
JOIN {test_table} v ON t.{id_col} = v.{id_col}
"""
# Run this in the DB — do not pull both tables to Python
with engine.connect() as conn:
    overlap = conn.execute(text(leakage_query)).scalar()
if overlap > 0:
    print(f"BLOCKER: {overlap} entity IDs appear in both train and test tables")
```

### Temporal leakage check

```python
temporal_query = f"""
SELECT
  MAX(CASE WHEN split = 'train' THEN {time_col} END) AS train_max,
  MIN(CASE WHEN split = 'validation' THEN {time_col} END) AS val_min
FROM {table}
"""
# Or join separate train/test tables on a timestamp column
```

**Pitfalls**:
- `ORDER BY RANDOM()` on PostgreSQL is slow on large tables — use `TABLESAMPLE BERNOULLI` instead
- BigQuery ADC requires `GOOGLE_APPLICATION_CREDENTIALS` or `gcloud auth application-default login`
- Snowflake connector needs `snowflake-sqlalchemy` + `snowflake-connector-python`
- `pd.read_sql` with large result sets loads everything into memory — always use sampling queries
- Column types from DB (e.g. `NUMERIC(10,2)`) map to Python `Decimal` not `float` — cast in SQL if needed

---

## Format Auto-Detection

When `--format` is not specified, detect format from file extension and content:

```python
from pathlib import Path
import json

def detect_format(path: str) -> str:
    # DB connection strings
    db_schemes = ("postgresql", "mysql", "sqlite", "bigquery", "snowflake", "duckdb")
    if any(path.startswith(s) for s in db_schemes):
        return "db"
    p = Path(path)
    if p.is_dir():
        # Check if it's a HF dataset (has dataset_info.json)
        if (p / "dataset_info.json").exists():
            return "hf"
        # Check if it's an image directory
        image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
        if any(f.suffix.lower() in image_exts for f in p.rglob("*") if f.is_file()):
            return "image-dir"
        # Assume Parquet directory
        return "parquet"
    suffix = p.suffix.lower()
    if suffix == ".csv":
        return "csv"
    if suffix == ".parquet":
        return "parquet"
    if suffix in {".jsonl", ".json"}:
        # Peek at first line to confirm
        with open(path) as f:
            first = f.readline()
        try:
            json.loads(first)
            return "jsonl"
        except json.JSONDecodeError:
            return "json"
    return "unknown"
```
