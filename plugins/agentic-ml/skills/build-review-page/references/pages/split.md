# split — Why can't the test rows have informed the model?

A score means nothing if the model, or the person tuning it, has seen the rows it is scored on. This page shows how the data was divided and how many times the locked part has been opened.

**Claim letter:** S

## Sources

- `review-target.json`: `split_strategy`, `split_manifest_path`, `test_keys_sha256`. Required.
- `splits/split-manifest.json`: `strategy`, `counts`, `fractions`, `label_distribution`, `time_ranges`, `gap`, `group_col`, `group_overlap`, `warnings`, `test_keys_sha256`. Required.
- `check-data-pipeline.json`: `checks_passed`, `checks_total`, `failures`. When present.
- `check-eval.json`: `protocol/split`, `protocol/final`, `protocol/test_evaluations`, `protocol/test_keys_sha256_match`. When present.

## Headline

State the mechanism, not the strategy name.

- Time split: "The model learns from <train range>; it is tested on <test range>, which it never saw."
- Group split: "No <group> appears on both sides of the split."
- Random split: "Rows were divided at random; nothing else separates them."

## Picture

One horizontal bar divided into train, validation, and test, sized by `counts`, each part labelled with its row count.

- For a time split, put the bar on a date axis from `time_ranges` and draw the `gap` as empty space.
- Draw the test part with a lock mark, and beside it the number of times it has been evaluated.

Bind the chart to `splits/split-manifest.json#/counts`.

## Facts to bind

- Rows in each part.
- The positive rate in each part, from `label_distribution`.
- For a group split: `group_col` and `group_overlap`.
- `protocol/test_evaluations`: how many times the test set has been scored.
- Pipeline checks passed out of the total, and each entry of `failures` by its `check` name.

## Only you can judge

- Can the same customer, patient, or device appear in more than one part under a different key?
- Was any of this data looked at to choose the label or the features before the split was made?
- Is the test period like the period the model will run in, or did something change in between?
- Is the gap long enough for labels to be known before training ends?

## Distrust this if

- `protocol/test_evaluations` is above one, or above zero while `protocol/final` is false.
- `protocol/test_keys_sha256_match` is false: the test rows are not the ones that were locked.
- The strategy is `random` or `stratified` and the manifest has a `time_col`.
- `group_overlap` is above zero.
- The positive rate differs sharply between parts.
- `warnings` in the manifest is not empty; show each warning.
- `failures` in the pipeline check is not empty.

## Leave out

Feature lists and model scores.
