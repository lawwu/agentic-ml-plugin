# JSON Output Schemas

Every skill writes a machine-readable JSON artifact alongside its text output. This file defines the schema for each skill artifact.

See [vocabulary.md](vocabulary.md) for canonical enum values.

## Base Schema

All artifacts share these top-level fields:

```json
{
  "schema_version": "1.0",
  "skill_name": "<kebab-case skill name>",
  "run_id": "<uuid or timestamp-slug shared across the orchestrated run>",
  "timestamp": "<ISO-8601 UTC>",
  "duration_seconds": 42.3,
  "decision": "GO | NO-GO | CONDITIONAL",
  "confidence": "high | medium | low",
  "summary": "<one-line human-readable summary>",
  "findings": [
    {
      "id": "F001",
      "severity": "blocker | high | medium | low",
      "title": "<short title>",
      "description": "<what was found>",
      "fix": "<recommended action>"
    }
  ],
  "next_commands": ["<exact shell command>"]
}
```

**Rules:**

- `run_id`: set by `orchestrate-e2e` and passed to sub-skills via `--run-id`; standalone invocations generate a local UUID
- `decision`: required for all skills; use `GO` when no gate decision applies (e.g., babysit-training completing successfully)
- `findings`: empty array `[]` when there are no findings — never omit the field
- `next_commands`: empty array `[]` when there are no next steps

---

## Per-Skill Extensions

### `review-target`

Written to: `<out-dir>/review-target.json`

```json
{
  "prediction_contract": {
    "entity": "<who/what>",
    "prediction_time": "<when>",
    "target_event": "<what outcome>",
    "horizon": "<how far ahead>"
  },
  "task_type": "classification | regression | ranking | forecasting",
  "label_formula": "<precise description>",
  "leakage_risks": [
    {"feature": "<name>", "severity": "blocker | high | medium | low", "mitigation": "<action>"}
  ],
  "primary_metric": "<metric name>",
  "promotion_threshold": "<value or description>",
  "split_strategy": "random | stratified | group-aware | time-based"
}
```

---

### `plan-experiment`

Written to: `<out-dir>/plan-experiment.json`

```json
{
  "hypothesis": "<falsifiable statement>",
  "task_type": "classification | regression | ranking | forecasting",
  "primary_metric": "<metric>",
  "total_budget_gpu_hours": 10.0,
  "candidates": [
    {
      "rank": 1,
      "model_family": "<name>",
      "rationale": "<why>",
      "estimated_gpu_hours": 1.5,
      "estimated_cost_usd": 4.5,
      "hp_search": {
        "<param>": {"range": [0.0001, 0.01], "scale": "log", "strategy": "random"}
      }
    }
  ],
  "success_criteria": {
    "primary": "<metric> >= <threshold> vs. baseline",
    "failure_trigger": "<condition>",
    "time_box_per_candidate": "<duration>"
  },
  "experiment_order": ["<candidate 1>", "<candidate 2>"]
}
```

---

### `build-baseline`

Written to: `<out-dir>/build-baseline.json`

```json
{
  "task_type": "classification | regression | ranking | forecasting",
  "data_source": "<path or dataset>",
  "label_col": "<col>",
  "primary_metric": "<metric>",
  "baselines": [
    {
      "method": "<name>",
      "description": "<what it does>",
      "score": 0.5,
      "is_best": true
    }
  ],
  "best_baseline": "<method name>",
  "best_score": 0.5
}
```

---

### `check-dataset-quality`

Written to: `<out-dir>/check-dataset-quality.json`

```json
{
  "data_source": "<path or dataset name>",
  "format": "<csv|parquet|jsonl|hf|image-dir|db>",
  "task_type": "<task or unknown>",
  "profile": {
    "train_rows": 50000,
    "validation_rows": 10000,
    "test_rows": 10000,
    "columns": ["<col1>", "<col2>"],
    "label_col": "<col>",
    "label_distribution": {"class_0": 0.61, "class_1": 0.39}
  },
  "blocker_count": 0,
  "high_count": 1,
  "medium_count": 2,
  "low_count": 3
}
```

---

### `check-data-pipeline`

Written to: `<out-dir>/check-data-pipeline.json`

```json
{
  "framework": "hf | torch | tf | jax",
  "model": "<model name or path>",
  "sample_size": 32,
  "task_type": "<task>",
  "checks_passed": 11,
  "checks_total": 13,
  "failures": [
    {
      "check": "<check name>",
      "expected": "<expected>",
      "actual": "<actual>",
      "location": "<file:line>",
      "fix": "<code change>"
    }
  ],
  "warnings": [
    {"check": "<check name>", "observation": "<text>"}
  ]
}
```

---

### `feature-engineer`

Written to: `<out-dir>/feature-engineer.json`

```json
{
  "business_outcome": "<text>",
  "label_col": "<col>",
  "entity_col": "<col>",
  "prediction_time": "<description>",
  "sources_explored": [
    {"name": "<table/dataset>", "rows": 100000, "usable_keys": ["<key>"], "notes": "<text>"}
  ],
  "feature_sets": [
    {
      "family": "<name>",
      "hypothesis": "<text>",
      "leakage_risk": "low | medium | high",
      "features": ["<f1>", "<f2>"]
    }
  ],
  "blocked_features": [
    {"feature": "<name>", "reason": "leakage | unavailable | unstable"}
  ],
  "baseline_feature_set": ["<feature1>", "<feature2>"],
  "implementation_paths": ["<script or snippet path>"]
}
```

---

### `babysit-training`

Written to: `<out-dir>/babysit-training.json`

```json
{
  "target": "<log path, PID, or cloud job ID>",
  "target_type": "local-log | remote-log | pid | vertex-pipeline | vertex-training | wandb | mlflow",
  "terminal_state": "SUCCEEDED | FAILED | CANCELLED | TIMEOUT",
  "total_steps": 5000,
  "final_metrics": {"loss": 0.342, "eval_f1": 0.881},
  "anomalies_detected": [
    {
      "step": 1432,
      "type": "nan-inf | oom | divergence | stalled | crash | checkpoint-failure | slow-throughput",
      "severity": "blocker | high | medium | low",
      "description": "<text>",
      "action_taken": "<text or none>"
    }
  ],
  "duration_seconds": 14400,
  "best_checkpoint": "<path or null>"
}
```

---

### `check-failed-run`

Written to: `<out-dir>/check-failed-run.json`

```json
{
  "run_status": "crashed | hung | degraded | diverged | recovered",
  "framework": "<detected or unknown>",
  "primary_cause": "nan-inf | oom | optimization-divergence | cuda-runtime | nccl-distributed | data-pipeline | config-error | io-checkpoint | stalled | process-crash | evaluation-mismatch | pipeline-orchestration | cloud-permissions-quota",
  "primary_cause_confidence": 0.86,
  "contributing_factors": ["<factor>"],
  "evidence": ["<evidence item>"],
  "root_cause": "<1-3 sentence explanation>",
  "fixes": [
    {
      "action": "<description>",
      "risk": "safe | needs-approval | dangerous",
      "expected_impact": "<text>",
      "validate": "<success criterion>"
    }
  ]
}
```

---

### `check-eval`

Written to: `<out-dir>/check-eval.json`

```json
{
  "checkpoint": "<path or model ID>",
  "strategy": "hf-trainer | lm-evaluation-harness | custom",
  "device": "<device>",
  "dtype": "<dtype>",
  "tasks": ["<task>"],
  "baseline": "<path or null>",
  "results": [
    {
      "task": "<task>",
      "metric": "<metric>",
      "score": 0.7823,
      "baseline_score": 0.7441,
      "delta": 0.0382,
      "regressed": false
    }
  ],
  "regressions": ["<metric name>"],
  "best_gain": {"metric": "<name>", "delta": 0.038},
  "notes": ["<warning or observation>"]
}
```

---

### `explain-model`

Written to: `<out-dir>/explain-model.json`

```json
{
  "model": "<path or ID>",
  "method": "shap | permutation | builtin",
  "dataset": "<path>",
  "dataset_rows": 10000,
  "protected_attributes": ["<attr>"],
  "top_features": [
    {"rank": 1, "feature": "<name>", "importance": 0.342, "shap_mean_abs": 0.28, "flags": []}
  ],
  "pdp_summary": [
    {"feature": "<name>", "shape": "monotonic | non-monotonic | step | interaction", "note": "<text>"}
  ],
  "bias_audit": [
    {
      "attribute": "<attr>",
      "metric": "disparate_impact | equalized_odds_tpr | predictive_parity",
      "value": 0.72,
      "threshold": 0.8,
      "passed": false
    }
  ],
  "unexpected_patterns": [
    {"pattern": "<description>", "severity": "blocker | warning | info", "action": "<text>"}
  ],
  "model_card_path": "<out-dir>/MODEL_CARD.md",
  "caveats": ["<caveat>"]
}
```

---

### `orchestrate-e2e`

Written to: `<out-dir>/run-summary.json`

```json
{
  "objective": "<business outcome>",
  "data_source": "<path or dataset>",
  "label_col": "<col>",
  "primary_metric": "<metric>",
  "budget_hours": 10,
  "gates": [
    {
      "gate_number": 1,
      "gate_name": "review-target | plan-experiment | build-baseline | check-dataset-quality | check-data-pipeline | feature-engineer | babysit-training | check-failed-run | check-eval | explain-model",
      "status": "PASS | FAIL | SKIPPED | PENDING",
      "artifact_path": "<out-dir>/<skill-name>.json",
      "timestamp": "<ISO-8601>",
      "decision": "GO | NO-GO | CONDITIONAL"
    }
  ],
  "report_path": "<out-dir>/report.html",
  "top_blockers": ["<blocker description>"],
  "top_risks": ["<risk description>"]
}
```

---

### `benchmark-e2e`

`benchmark-e2e` is a meta-skill and does not emit a standard gate artifact. It writes its own report to `<out-dir>/benchmark-report.json` with run-level telemetry:

```json
{
  "schema_version": "1.0",
  "skill_name": "benchmark-e2e",
  "run_id": "<uuid>",
  "timestamp": "<ISO-8601>",
  "duration_seconds": 3600,
  "decision": "GO",
  "confidence": "high",
  "summary": "<one-line summary>",
  "findings": [],
  "next_commands": [],
  "selected_scenario": "hard-fraud | hard-attrition | xhard-churn",
  "scenario_detection": "auto | user-forced",
  "modes": ["no-plugin", "plugin", "automl"],
  "runs_per_cell": 1,
  "primary_metric": "<metric>",
  "results": [
    {
      "mode": "no-plugin | plugin | automl",
      "scenario": "<scenario>",
      "quality_score": 78,
      "reliability_score": 90,
      "efficiency_score": 65,
      "ops_readiness_score": 80,
      "total_score": 78,
      "loc_run": 142,
      "tokens_in": 15000,
      "tokens_out": 3200,
      "tokens_total": 18200
    }
  ],
  "recommendation": {
    "default_mode": "plugin",
    "default_mode_rationale": "<text>",
    "fallback_mode": "no-plugin",
    "fallback_mode_rationale": "<text>"
  }
}
```
