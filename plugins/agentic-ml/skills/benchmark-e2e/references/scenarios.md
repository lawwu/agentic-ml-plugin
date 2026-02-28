# Scenarios

Use these definitions to classify exactly one scenario per benchmark run.

## clean-kaggle

Representative characteristics:

- mostly clean schema
- obvious label column
- low missingness
- standard train/validation split

Typical goal:

- maximize baseline speed and quality with low remediation overhead.

## messy-data

Representative characteristics:

- missing labels/values
- schema inconsistencies across splits/tables
- duplicate entities and leakage risk
- noisy categorical/text fields

Typical goal:

- maximize reliability and failure recovery while preserving quality.

## Scenario setup checklist

For the selected scenario, document:

- dataset source and snapshot path
- label and task type
- split policy
- known issues injected or observed

Use [datasets.md](datasets.md) for canonical dataset options. Recommended clean baseline: `adult-census-income`.

## Automatic scenario identification (choose one)

When `--scenario auto` is used, classify with this protocol:

1) Collect quick signals:
- missing-label rate in target column
- max null rate across key feature columns
- schema consistency across splits/tables
- duplicate/leakage signals (row duplicates, cross-split entity overlap)
- parse/encoding/load errors

2) Mark `messy-data` if any of the following are true:
- missing labels > 1%
- any key feature null rate > 5%
- schema mismatch across splits/tables
- cross-split entity overlap detected
- parse/encoding/load errors are present

3) Otherwise mark `clean-kaggle`.

4) Output exactly one label: `clean-kaggle` or `messy-data`.

If evidence is incomplete or mixed, default to `messy-data` (conservative classification).
