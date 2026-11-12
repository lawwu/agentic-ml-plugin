# baseline — Is it better than the simple alternative, beyond noise?

The claim a reviewer is most often asked to accept. The page shows the model next to what the team would do without it, with the uncertainty drawn, so a gain that could be luck looks like one.

**Claim letter:** B

## Sources

- `build-baseline.json`: `baselines` (`method`, `kind`, `description`, `score`, `ci`, `is_best`), `best_baseline`, `best_score`, `primary_metric`. Required.
- `check-eval.json`: `results/0` (`metric`, `score`, `ci`, `n`, `baseline_score`, `baseline_ci`, `delta`, `delta_ci`, `regressed`), `protocol/split`, `protocol/final`. Required once a model is trained.
- `review-target.json` → `promotion_threshold`. When present.
- `train-model.json` → `sweep/trials`. When present.

Before a model exists, build the page from `build-baseline.json` alone, with the headline "The bar to beat is <best baseline> at <score>."

## Headline

Decide from `delta_ci`, for a metric where higher is better (reverse for an error metric):

- Both ends above zero: "Better than <best baseline>, and the gap is larger than the noise."
- The interval contains zero: "Not shown to be better than <best baseline>."
- Both ends below zero: "Worse than <best baseline>."

## Picture

Two panels sharing the page width.

1. **Scores.** One row per baseline and one for the model, on a single axis in the metric's units. Each row is a dot at the score with a line across its interval. Label each row with the method name and its score. The model row is last and stands out.
2. **The gap.** One dot at `delta` with a line across `delta_ci`, on an axis that includes zero, with zero drawn as a rule. This panel answers the question; give it room. When the promotion bar gates one metric and the product is run on another, draw a gap row for each and say which one is gated.

Bind the chart to `check-eval.json#/results/0`.

## Facts to bind

- The model's score with its interval.
- The best baseline: its name, what it does (`description`), and its score with its interval.
- `delta` with `delta_ci`.
- `n`, and which rows the scores come from (`protocol/split`).
- The metric's name, with one clause on what it measures.

## Only you can judge

- Is the best baseline what the team would really do without a model? If a stronger simple rule exists, name it.
- Is a gain of this size worth owning a model for?
- Is this metric the one the decision depends on?
- Would the result surprise someone who knows the domain? If so, in which direction?

## Distrust this if

- `delta_ci` contains zero.
- The interval on the gap is wider than the gap itself, on any metric shown.
- The gated metric is not the one the product is run on.
- `protocol/split` is `val` and `sweep/trials` is large: the best of many tries looks better than it is.
- `protocol/split` is `test` while `protocol/final` is false.
- No baseline has kind `non-ml`.
- `regressed` is true.
- `train-model.json` has a `too-good-to-be-true` preflight check that did not pass.

## Leave out

Slices, calibration, and feature importance. Those are on the errors page.
