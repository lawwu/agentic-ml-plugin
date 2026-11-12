# label — What is predicted, and when is the truth known?

Most wrong models are right about the wrong thing. This page lets a person who knows the business confirm that the label is the event they care about and that nothing from the future reaches the model.

**Claim letter:** L

## Sources

- `review-target.json`: `prediction_contract` (`entity`, `prediction_time`, `target_event`, `horizon`), `label_formula`, `task_type`, `leakage_risks`, `primary_metric`, `promotion_threshold`, `split_strategy`, `test_keys_sha256`. Required.

## Headline

One plain sentence in the form: "At <prediction time>, predict whether <target event> within <horizon>." Say it the way you would to someone outside the team. The contract's exact wording goes in the facts, bound and unshortened, so the reviewer can compare the two.

## Picture

A timeline, left to right:

- a band labelled "what the model may use" ending at the prediction time
- a marker at the prediction time
- the horizon as a span to the right
- a marker where the truth becomes known

Below the timeline, place each entry of `leakage_risks` as a labelled tick with its severity. Bind the chart to `review-target.json#/prediction_contract`.

## Facts to bind

- The contract word for word: `entity`, `prediction_time`, `target_event`.
- `label_formula`, in full. This is the sentence the reviewer most needs to read.
- `primary_metric`, with one clause saying what it measures and what chance looks like.
- `promotion_threshold`: the bar the model must clear.
- `split_strategy`.
- Each leakage risk rated `blocker` or `high`: the feature and its `mitigation`.

## Only you can judge

- Is the target event what the business acts on, or a stand-in for it? If a stand-in, what does it miss?
- At the prediction time, would every input really be on hand, in the form the model sees?
- Is the horizon the one the decision needs, or the one the data made easy?
- Would you defend the promotion bar to the person who pays for a wrong prediction?
- Who must agree before this definition changes?

## Distrust this if

- A leakage risk is rated `blocker` or `high` and its `mitigation` is empty.
- `split_strategy` is `random` or `stratified` while the contract has a prediction time: later rows can leak into training.
- `promotion_threshold` is a phrase with no number.
- `test_keys_sha256` is missing: the test set is not locked yet.
- `horizon` is empty or vague ("soon", "later").

## Leave out

Data profiles and scores. They belong on the split and baseline pages.
