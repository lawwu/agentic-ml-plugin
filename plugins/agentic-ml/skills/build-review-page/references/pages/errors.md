# errors — Where is it wrong?

An average hides the cases that hurt. This page shows the groups where the model is weakest, whether its probabilities can be taken at face value, and what it leans on.

**Claim letter:** E

## Sources

- `check-eval.json`: `slices` (`col`, `value`, `n`, `point`, `ci`, `flagged`), `results/0/score`, `calibration`, `notes`. Required.
- `explain-model.json`: `top_features`, `bias_audit`, `unexpected_patterns`, `caveats`. When present.

If `slices` is empty, do not build the page. Record it as omitted: "no slices were evaluated; rerun check-eval with slice columns".

## Headline

Name the weakest place. "Weakest on <column> = <value>: <score> against <overall> overall." If no slice is flagged: "No evaluated group falls clearly below the overall score."

## Picture

One row per slice, weakest at the top, at most eight rows: every flagged slice, then the weakest of the rest.

- A dot at `point` with a line across `ci`.
- A vertical rule at the overall score, labelled.
- Each row labelled with the column, the value, and `n`.
- Flagged rows stand out by color and by a text mark, not color alone.

Bind the chart to `check-eval.json#/slices`.

## Facts to bind

- The weakest slice: its score, interval, and `n`.
- How many slices were evaluated and how many are flagged (counts).
- Calibration: `calibration/ece`, with the clause "the average gap between the probability the model states and how often it is right".
- The top feature and its `importance`, and what the feature is, in plain words.
- Each failed entry of `bias_audit`: the attribute, the metric, `value`, and `threshold`.
- Each entry of `unexpected_patterns` rated `blocker` or `high`.

## Only you can judge

- Is the weakest group one where a mistake is costly, sensitive, or visible?
- Does the top feature make sense as a reason, or could it be a stand-in for the outcome?
- Which group that matters to the business was not sliced?
- No artifact holds individual wrong predictions. Do you want to read ten of them before approving?

## Distrust this if

- A slice's interval is wider than the distance between its score and the overall score: the weakness may be noise, or a real one may be hidden.
- Any `bias_audit` entry has `passed` false.
- One feature carries more than half of the total importance.
- `calibration` is missing while the model's probabilities are used to set a cutoff.
- `protected_attributes` is empty: no fairness check was run.
- Fewer than three columns were sliced.

## Leave out

The overall comparison with the baseline; link to that page.
