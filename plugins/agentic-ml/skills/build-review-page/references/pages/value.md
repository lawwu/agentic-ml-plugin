# value — What does acting at this cutoff cost and gain?

A model is used at one cutoff, by people with limited time. This page shows what happens at that cutoff and which of the inputs behind the value estimate are measured and which are assumed.

**Claim letter:** V

## Sources

- `check-eval.json`: `operating_point` (`threshold`, `precision`, `recall`, `flagged_rate`), `protocol/split`. Required.
- `demonstrate-value.json`: `business_context`, `business_impact`, `assumptions`, `evidence_verified`. When present.

The cutoff may be a rule instead of a score threshold ("the top ten a day"). Then describe the rule in its own terms, and compare it with the same rule applied to the best baseline when the artifact has that.

If `operating_point` is missing, do not build the page. Record it as omitted: "no cutoff was chosen; rerun check-eval with a threshold".

## Headline

Describe the cutoff by what a person experiences. "At this cutoff the model flags <flagged rate> of cases, is right about <precision> of them, and catches <recall> of the real ones."

## Picture

Three horizontal bars, each a share of a whole, each labelled in words with its bound value:

1. Of all cases, the share flagged (`flagged_rate`).
2. Of flagged cases, the share that are real (`precision`). The remainder is labelled "false alarms".
3. Of real cases, the share caught (`recall`). The remainder is labelled "missed".

Draw the bars to scale from the three values. Do not convert them to counts or money: that arithmetic belongs to `demonstrate-value`, which records it as evidence.

Bind the chart to `check-eval.json#/operating_point`.

## Facts to bind

- `threshold`, `precision`, `recall`, `flagged_rate`.
- Each entry of `business_impact`: its `description` and `estimated_value`, as written.
- Each entry of `assumptions`: the input, its value, and its `source`, with `assumed` inputs set apart from `user-provided` ones.
- Which rows the cutoff was chosen on (`protocol/split`).

## Only you can judge

- Can the people who act on a flag handle this many?
- Which is worse here, a false alarm or a miss? The cutoff should follow from that.
- Are the inputs marked `user-provided` still true?
- Who owns the cutoff after launch, and what would make them move it?

## Distrust this if

- Any assumption has source `assumed`.
- `evidence_verified` is false.
- `protocol/split` is `test`: a cutoff chosen on test rows makes the test score optimistic.
- Any `estimated_value` is null: the impact is a direction, not an amount.
- `demonstrate-value.json` is missing: no value estimate exists, only rates.
- No interval is recorded for precision or recall: both could move with a different sample.
- The share caught and the share right come from different rows (one from validation, one from test).

## Leave out

Ranking metrics. A reader acting at a cutoff does not need the area under a curve.
