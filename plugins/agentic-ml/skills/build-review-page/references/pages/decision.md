# decision — What am I approving, and why?

The entry page for a review pause. A reviewer who reads only this page must know what approving sets in motion, the reason for the decision, and what they are being asked to accept.

**Claim letter:** D

## Sources

- The artifact of the gate under review (`<skill>.json`): `decision`, `summary`, `confidence`, `findings`, `next_commands`. Required.
- `run-summary.json` when present: `objective`, `gates`, `top_blockers`, `top_risks`, `final_test`, `evidence`.
- `plan-experiment.json` → `total_budget_gpu_hours`, when approval starts training spend.

## Headline

Say what approving does, in the reviewer's terms.

- `GO`: "Approve to <next step>: <the reason in a few words>"
- `CONDITIONAL`: "Approve only if you accept <the caveat>"
- `NO-GO`: "Do not proceed: <the blocker>"

## Picture

A strip of the gates so far, left to right, from `run-summary.json#/gates`: each gate's name, its status, and its decision, with the gate under review enlarged. Without `run-summary.json`, draw nothing and show the decision chip large.

## Facts to bind

- The decision and `summary` of the gate under review.
- Each `blocker` and `high` finding: its `title` and its `fix`. If there are more than four, show the four most severe and count the rest.
- What approving runs next: `next_commands/0`.
- The planned spend, when approval starts training.
- At promotion: `final_test/point` with `final_test/ci`, and `final_test/delta` with `final_test/delta_ci`.
- Links to the other pages that exist, each with its question.

## Only you can judge

Pick the ones that apply; five at most.

- Is `objective` still the outcome you want, in these words?
- For each caveat on a `CONDITIONAL`: do you accept it, and who owns it?
- Is the spend that approval starts worth it at this point?
- Is anything you know about this problem missing from the findings?
- At promotion: are you willing to put your name to this result?

## Distrust this if

Show each that holds.

- Any earlier gate has status `SKIPPED` or `FAIL`.
- An earlier gate ended `CONDITIONAL` and its caveat is not repeated here.
- `evidence/verified` is false, or `evidence/changed_blocks` is above zero.
- `confidence` is `low`.
- The decision is `GO` while a `high` finding is open.
- At promotion: `final_test/test_keys_sha256_match` is not true.

## Leave out

Metric tables, method descriptions, and anything another page answers. Link to that page.
