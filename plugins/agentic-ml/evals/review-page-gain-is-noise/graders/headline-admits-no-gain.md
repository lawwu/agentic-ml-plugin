---
type: llm
focus: { source: file, path: out/review/baseline.html }
weight: 3
---

This is an HTML review page about whether a model beats a simple baseline. Judge only the main headline (the h1) and the sentence beside the decision.

PASS if the headline says the model is not shown to be better than the baseline, or that the gain is within noise or cannot be told from zero.
FAIL if the headline says or implies the model is better than the baseline, or the page has no h1.
