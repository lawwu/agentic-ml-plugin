---
type: regex
pattern: 'data-ref="check-eval\.json#/decision"[^>]*>\s*NO-GO'
target: { source: file, path: out/review/baseline.html }
weight: 2
---
