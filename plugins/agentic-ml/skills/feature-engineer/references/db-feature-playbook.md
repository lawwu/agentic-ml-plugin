# DB Feature Playbook

Use this workflow when features come from relational/warehouse tables.

## 1) Source inventory

For each table:

- grain (row meaning)
- entity key columns
- timestamp columns
- expected join path to label entity
- row count and active time range

## 2) Joinability checks

Validate before feature creation:

- key coverage from label table to feature table
- one-to-many vs many-to-many join behavior
- duplicate amplification risk after joins

## 3) Point-in-time safe joins

Use as-of logic to avoid future leakage:

```sql
SELECT
  l.entity_id,
  l.prediction_time,
  f.*
FROM labels l
LEFT JOIN features f
  ON f.entity_id = l.entity_id
 AND f.event_time <= l.prediction_time
```

For windowed aggregates:

```sql
SELECT
  l.entity_id,
  l.prediction_time,
  COUNT(*) AS events_30d,
  SUM(x.amount) AS amount_30d
FROM labels l
LEFT JOIN events x
  ON x.entity_id = l.entity_id
 AND x.event_time > l.prediction_time - INTERVAL '30 day'
 AND x.event_time <= l.prediction_time
GROUP BY 1,2
```

## 4) Profiling queries

Run cheap profiling before materialization:

- `COUNT(*)`
- `COUNT(DISTINCT entity_id)`
- null rate per candidate feature
- min/max event time
- join hit rate against label table

## 5) Materialization guidance

- Keep one row per prediction entity/time in the final training set.
- Persist feature SQL in versioned files, not ad hoc notebook cells.
- Add validation queries for duplicate keys and null-label rows.
