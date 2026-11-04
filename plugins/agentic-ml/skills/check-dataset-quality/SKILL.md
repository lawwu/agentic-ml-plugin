---
name: check-dataset-quality
description: Profile and validate a dataset before training. Works with CSV, Parquet, JSONL, HuggingFace datasets, image directories, and database tables (PostgreSQL, MySQL, BigQuery, SQLite, Snowflake). Checks for missing values, duplicates, class imbalance, split leakage, outliers, schema drift, personal data, and format issues. Produces a severity-rated audit report with a Go/No-Go recommendation, and saves a data contract and drift baseline from the training split. Triggers automatically when asked to check, audit, validate, or profile a dataset or table.
argument-hint: "<path-or-hf-dataset-or-table> [--split train|validation|test] [--db-url DSN] [--db-query SQL] [--text-col COLUMN] [--label-col COLUMN] [--id-col COLUMN] [--task classification|regression|language-modeling|image-classification] [--sample N] [--format csv|parquet|jsonl|hf|image-dir|db] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Dataset Audit

Profile and validate a dataset for ML readiness. Identify blockers and quality issues before they cause silent model failures.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `path/to/data.csv` — local CSV file
- `path/to/data.parquet` — local Parquet file
- `path/to/data.jsonl` — local JSONL file
- `hf://owner/dataset-name` or bare `owner/dataset-name` — HuggingFace Hub dataset
- `path/to/images/` — image directory (expected: per-class subdirs)
- `schema.table_name` or `database.schema.table` — database table (requires `--db-url`)
- `--db-url DSN` — SQLAlchemy-compatible connection string (e.g. `postgresql://user:pass@host/db`, `bigquery://project/dataset`, `sqlite:///path/to/db.sqlite`)
- `--db-query SQL` — audit the result of an arbitrary SQL query instead of a whole table
- `--split` — which split(s) to load for file-based sources (default: all available)
- `--text-col` — primary text column for NLP tasks
- `--label-col` — target/label column
- `--id-col` — unique entity identifier for leakage detection
- `--task` — task type to tailor checks
- `--sample N` — row cap for large datasets/tables (default: full scan up to 1M rows; for DB uses `TABLESAMPLE` or `LIMIT`)
- `--format` — force format detection (use `db` to skip file detection)

Target: `$ARGUMENTS`

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`, else `senior`) and follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- `junior`: name each pitfall (e.g. "target leakage", "entity overlap") and say how it would inflate metrics.
- `staff`: summary lists blockers and high findings only.

## Your responsibilities

### 1. Load and profile

See [references/format-loading.md](references/format-loading.md) for efficient loading per format.

Establish a quick profile before running checks:

- Row and column counts per split
- Detected format and encoding
- Column names, dtypes, and type coercion failures
- Memory footprint estimate
- Sample of first 5 rows

Report the profile before proceeding to checks.

### 2. Run core quality checks

Always run these regardless of task type:

**Structural checks**

- Schema consistency: same column names and types across train/validation/test
- Parse errors: rows that fail to load, truncated JSONL lines, corrupt Parquet row groups
- Encoding issues: mojibake, null bytes, mixed encodings in text columns

**Missingness**

- Per-column null rate per split
- Columns with missingness that varies significantly between splits (> 5pp delta)
- Missing labels (null or empty in `--label-col`)

**Duplicates**

- Exact row duplicates within each split
- Near-duplicate detection on text column (MinHash or length+prefix heuristic)
- `--id-col` duplicates within a split (entity appears twice)
- Cross-split `--id-col` overlap (leakage)

**Label health** (when `--label-col` provided)

- Classification: class distribution, imbalance ratio, rare classes (< 0.5%)
- Regression: target distribution, extreme skew, zero inflation, impossible values
- NLP: sequence length distribution, empty sequences, truncation risk at model max_length

**Outliers and value sanity**

- Numeric columns: IQR-based outlier rate, impossible values (negative age, etc.)
- Text columns: extreme length outliers (< 5 tokens or > 10× median)
- Image directories: corrupt/unreadable files, extreme aspect ratios, near-zero size

**Leakage checks**

- Direct leakage: `--label-col` value appears verbatim in text features
- Cross-split entity overlap via `--id-col`
- Train rows with timestamps newer than validation/test (if timestamp column detected)

**Splits** (when `<out-dir>/splits/` exists from `review-target`)

- Audit each split separately, and check cross-split leakage on the actual `train` / `val` / `test` keys
- Profile only the row counts and label rates of `test` — do not explore its feature values

**Personal data**

- Columns whose names suggest personal data (name, email, phone, address, ssn, dob, ip, device id)
- Text columns matching email, phone, card-number, or national-ID patterns (sample rows; report counts, never the values)
- Severity: `high` when personal data would be used as a feature or sent to an external service; `medium` otherwise. Recommend dropping, hashing, or tokenizing.
- For LLM fine-tuning data: also check overlap between training examples and the evaluation set (contamination) — exact and near-duplicate matches are blockers

Run task-specific checks from [references/audit-checks.md](references/audit-checks.md).

Use [`uv run "${CLAUDE_SKILL_DIR}/scripts/profile-dataset.py" <path> ...`](scripts/profile-dataset.py) for efficient statistical profiling when the dataset is local. For database targets, push as much computation as possible to the DB engine (COUNT, NULL rates, MIN/MAX, APPROX_COUNT_DISTINCT) rather than pulling all rows — see [references/format-loading.md](references/format-loading.md).

### 3. Severity classification

| Severity | Meaning |
|---|---|
| `blocker` | Invalidates evaluation or training; must be fixed before proceeding |
| `high` | Strong risk of instability, bias, or silent failure |
| `medium` | Quality debt; worth fixing before production |
| `low` | Informational; monitor but not urgent |

**Blocker examples**: cross-split leakage, missing labels in > 20% of train, schema mismatch that breaks inference, corrupt Parquet that prevents loading.

If any blocker exists, recommend **NO-GO** explicitly.

### 4. Recommend concrete remediation

Each finding must include:

- Affected columns, splits, and row counts
- Why it matters for model quality
- One or two concrete fixes with code or commands
- Re-check criterion

Prefer remediations that preserve data provenance and are reproducible.

### 5. Save the data contract and drift baseline

When the data is tabular, record what "normal" training data looks like, so the same checks can run at retraining and in production:

```bash
uv run "${CLAUDE_SKILL_DIR}/scripts/data_contract.py" build --data <path> \
  --splits <out-dir>/splits --split train --label-col <col> [--exclude-cols <id,ts>] --out-dir <out-dir>
```

Input is CSV; convert Parquet first. This writes:

- `data-contract.json` — per column: type, nullability, observed range or allowed values, and role
- `training-profile.json` — per feature: quantile bins or category frequencies from `train` (the drift baseline)

To check new data against them later (a new extract, `val`, or a production sample):

```bash
uv run "${CLAUDE_SKILL_DIR}/scripts/data_contract.py" validate --contract <out-dir>/data-contract.json \
  --profile <out-dir>/training-profile.json --data <new.csv> --out <out-dir>/contract-validation.json
```

It reports schema violations and per-feature PSI drift (stable < 0.1, moderate 0.1–0.25, major > 0.25). Validating `val` against the contract is a quick check that the split did not create a distribution shift.

### 6. Output format

```text
Dataset Audit Report
====================
Path: <path or dataset name>
Format: <detected format>
Task: <task or unknown>

Profile:
- train: <N> rows × <M> cols  |  validation: <N> rows  |  test: <N> rows
- Columns: <list>
- Label col: <col> (<class distribution or range>)

Blockers:
1) <finding> — affects <splits/cols> — fix: <action>

High:
1) <finding> — affects <splits/cols> — fix: <action>

Medium:
1) <finding>

Low:
1) <finding>

Recommended actions (ordered by priority):
1) ...
2) ...

Decision: GO | NO-GO
Confidence: high|medium|low
```

### Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- per-split row counts and label rates (never feature values from `test`)
- for each `blocker` and `high` finding: the query or computation that shows it, printing counts and rates only
- for database sources: the pushed-down read-only SQL and its aggregate result; reference the DSN through an environment variable, never inline credentials

### JSON artifact

Write `check-dataset-quality.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:

- `decision`: `GO` / `NO-GO`
- `profile`: row/column counts, label distribution
- `blocker_count`, `high_count`, `medium_count`, `low_count`
- `findings`: one entry per finding from the audit report with appropriate severity
- `data_contract_path`, `training_profile_path` when saved
- `provenance`: data path, size, and sha256 for every file audited (`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/provenance.py" --data <path>`, using the project's interpreter)

### 7. Stop conditions

Stop when:

- A complete severity-ranked audit report is delivered with Go/No-Go
- Required clarification (unknown label column, format ambiguity) is explicitly requested
- Dataset cannot be loaded and the error is clearly reported

## Quick heuristics

- Any `--id-col` overlap between train and test → blocker leakage
- Validation accuracy too high too fast → check leakage before trusting the number
- Schema drift between splits → silent feature-engineering bugs at inference time
- Rare class < 0.5% in classification → metric masking; use macro F1 or PR-AUC
- Empty or near-empty text fields → tokenizer produces degenerate sequences
- Class label strings that differ only in case or whitespace → silent label noise

## Example

```text
/agentic-ml:check-dataset-quality hf://allenai/c4 --split train --text-col text --task language-modeling --sample 50000

Dataset Audit Report
====================
Path: allenai/c4 (HuggingFace Hub, split=train, sampled 50,000 rows)
Format: HF datasets (Arrow)
Task: language-modeling

Profile:
- train: 50,000 rows × 2 cols (text, timestamp)
- Columns: text (string), timestamp (string, parseable as datetime)
- Label col: none

Blockers:
none

High:
1) Sequence length distribution: p99=8,412 tokens (GPT-2 tokenizer). If max_length=1024, 23% of examples will be truncated to <50% of their content.

Medium:
1) 142 rows (0.28%) contain near-duplicate text (≥ 0.95 Jaccard similarity).
2) 38 rows have text length < 20 characters; likely navigation fragments.

Recommended actions (ordered by priority):
1) Use packing/concatenation (datasets.map with stride) to avoid truncation waste.
2) Filter rows with char_count < 50 before tokenization.

Decision: GO
Confidence: high
```

```text
/agentic-ml:check-dataset-quality ml.training_examples --db-url postgresql://user:pass@host/prod --label-col label --id-col user_id --task classification --sample 200000

Dataset Audit Report
====================
Source: postgresql://host/prod → ml.training_examples (sampled 200,000 rows via TABLESAMPLE)
Format: database table
Task: classification

Profile:
- rows: 200,000 × 14 cols
- Columns: user_id (int8), text (text), label (int2), created_at (timestamptz), ...
- Label col: label (0: 61%, 1: 39%)

Blockers:
1) 3,812 user_id values appear in both ml.training_examples and ml.test_examples — cross-table entity leakage.

High:
1) label is NULL in 4.2% of rows (8,400 rows).
2) text column has 0-character strings in 1.1% of rows.

Recommended actions (ordered by priority):
1) Rebuild train/test split with GROUP BY user_id to prevent entity overlap.
2) Filter or impute NULL labels before training.

Decision: NO-GO
Confidence: high
```

## Additional resources

- [references/audit-checks.md](references/audit-checks.md) — Detailed check specifications with thresholds and severity criteria
- [references/format-loading.md](references/format-loading.md) — Efficient loading patterns per format
- [scripts/profile-dataset.py](scripts/profile-dataset.py) — Dataset profiling script (run with `uv run`) that outputs JSON stats
- [scripts/data_contract.py](scripts/data_contract.py) — builds the data contract and drift baseline, and validates new data against them
