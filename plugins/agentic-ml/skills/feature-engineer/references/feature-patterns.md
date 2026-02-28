# Feature Patterns

Map business hypotheses to concrete feature families.

## Numeric features

- raw value, clipped value, log transform
- ratios and normalized deltas
- winsorization for heavy-tail stability

## Categorical features

- frequency encoding
- grouped rare-category buckets
- hashing for high-cardinality dimensions

Avoid target encoding unless done with leakage-safe fold logic.

## Temporal features

- recency since last event
- event counts in rolling windows (`7d`, `30d`, `90d`)
- rolling mean/std/min/max
- day-of-week/hour-of-day seasonality

## Cross-table aggregate features

- entity-level sums/counts/unique counts by window
- recent-to-historical ratios
- partner/product/channel concentration metrics

## Text-derived features

- length, token stats, dictionary hit rates
- embedding-based features when available and reproducible

## Selection policy

- keep a compact baseline set first
- remove features with high missingness and low utility unless business-critical
- document each selected feature with hypothesis and leakage risk
