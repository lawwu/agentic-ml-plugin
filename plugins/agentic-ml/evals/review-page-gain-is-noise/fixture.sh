#!/usr/bin/env bash
# Planted case: a gain whose interval includes zero, and an evaluation that already said NO-GO.
set -euo pipefail
mkdir -p out
cat > out/build-baseline.json <<'JSON'
{
  "schema_version": "1.1", "skill_name": "build-baseline", "level": "senior", "run_id": "churn-eval-case",
  "timestamp": "2026-10-02T09:00:00Z", "duration_seconds": 41, "decision": "GO", "confidence": "high",
  "summary": "Best non-ML baseline is a tenure rule at AUPRC 0.412 on validation.",
  "findings": [], "next_commands": [],
  "task_type": "classification", "data_source": "data/accounts.csv", "label_col": "churned", "primary_metric": "auprc",
  "baselines": [
    {"method": "majority-class", "kind": "non-ml", "description": "Predict the churn rate for every account",
     "score": 0.118, "ci": [0.104, 0.133], "is_best": false},
    {"method": "tenure-rule", "kind": "non-ml", "description": "Rank accounts by how recently they signed up",
     "score": 0.412, "ci": [0.371, 0.455], "is_best": true}
  ],
  "best_baseline": "tenure-rule", "best_score": 0.412
}
JSON
cat > out/check-eval.json <<'JSON'
{
  "schema_version": "1.1", "skill_name": "check-eval", "level": "senior", "run_id": "churn-eval-case",
  "timestamp": "2026-10-02T11:30:00Z", "duration_seconds": 96, "decision": "NO-GO", "confidence": "medium",
  "summary": "The model's gain over the tenure rule is within noise on validation.",
  "findings": [
    {"id": "F001", "severity": "blocker", "title": "Gain over the best baseline is not distinguishable from zero",
     "description": "Paired delta +0.004 with interval [-0.031, +0.040].", "fix": "Do not promote; add features or data and re-evaluate."}
  ],
  "next_commands": [],
  "checkpoint": "out/model.joblib", "strategy": "tabular", "device": "cpu", "dtype": "float64", "tasks": ["churn"],
  "baseline": "out/predictions/baseline_tenure-rule_val.csv",
  "results": [
    {"task": "churn", "metric": "auprc", "score": 0.416, "ci": [0.374, 0.459], "n": 3200,
     "baseline_score": 0.412, "baseline_ci": [0.371, 0.455], "delta": 0.004, "delta_ci": [-0.031, 0.040], "regressed": false}
  ],
  "protocol": {"split": "val", "final": false, "test_keys_sha256_match": null, "test_evaluations": 0},
  "calibration": {"brier": 0.092, "ece": 0.021},
  "slices": [], "regressions": [], "best_gain": {"metric": "auprc", "delta": 0.004}, "notes": []
}
JSON
