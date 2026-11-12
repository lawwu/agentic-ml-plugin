# JSON Output Schemas

Every skill writes a machine-readable JSON artifact alongside its text output. This file defines the schema for each skill artifact.

See [vocabulary.md](vocabulary.md) for canonical enum values.

## Base Schema

All artifacts share these top-level fields:

```json
{
  "schema_version": "1.1",
  "skill_name": "<kebab-case skill name>",
  "level": "junior | senior | staff",
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
  "next_commands": ["<exact shell command>"],
  "evidence_notebook": "<out-dir>/evidence.md",
  "evidence_blocks": 3,
  "provenance": {
    "created_at": "<ISO-8601 UTC>",
    "git": {"sha": "<sha>", "dirty": false, "branch": "<branch>"},
    "env": {"python": "3.12.4", "packages": {"scikit-learn": "1.6.1"}},
    "lockfiles": [{"path": "uv.lock", "sha256": "<sha256>"}],
    "data": [{"path": "<path>", "bytes": 1234, "sha256": "<sha256>"}],
    "seed": 42,
    "split_manifest": {"path": "<out-dir>/splits/split-manifest.json", "test_keys_sha256": "<sha256>"}
  }
}
```

**Rules:**

- `run_id`: set by `orchestrate-e2e` and passed to sub-skills via `--run-id`; standalone invocations generate a local UUID
- `decision`: required for all skills; use `GO` when no gate decision applies (e.g., babysit-training completing successfully)
- `findings`: empty array `[]` when there are no findings — never omit the field
- `next_commands`: empty array `[]` when there are no next steps
- `level`: the resolved user level ([levels.md](levels.md)); it changes communication and autonomy only, never thresholds
- `provenance`: required for skills that read data or run code (from `scripts/provenance.py`, run with the project's interpreter — e.g. `uv run python`, not `uv run provenance.py`); omit for skills that only read other artifacts
- `findings[]` may carry `evidence` (`[{"kind": "notebook|command|query|file|stat", "ref": "<evidence.md, command, or path>", "section": "<notebook heading>", "command": "<exec command>", "excerpt": "<short output>"}]`) — include it whenever a finding rests on a computed number; prefer `notebook` entries
- `evidence_notebook` / `evidence_blocks`: the run's [evidence notebook](evidence-notebook.md) and the number of `exec` blocks this skill added to it
- Version history: `1.1` added `level`, `provenance`, `evidence_notebook`, and `evidence_blocks`; `1.0` artifacts remain readable

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
  "split_strategy": "random | stratified | group | time",
  "split_manifest_path": "<out-dir>/splits/split-manifest.json",
  "test_keys_sha256": "<sha256 of sorted test row keys>"
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
      "kind": "non-ml | statistical | foundation-model",
      "description": "<what it does>",
      "rule": {"<param>": "<fitted value>"},
      "score": 0.5,
      "ci": [0.46, 0.54],
      "predictions_path": "<out-dir>/predictions/baseline_<method>_val.csv",
      "is_best": true
    }
  ],
  "split_manifest_path": "<out-dir>/splits/split-manifest.json",
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
  "low_count": 3,
  "data_contract_path": "<out-dir>/data-contract.json",
  "training_profile_path": "<out-dir>/training-profile.json"
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
  "terminal_state": "SUCCEEDED | FAILED | CANCELLED | TIMEOUT | EARLY_STOPPED",
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

`primary_cause_confidence` is the probability that the primary cause is correct. The base `confidence` field must agree with it — see [vocabulary.md](vocabulary.md#confidence).

---

### `check-eval`

Written to: `<out-dir>/check-eval.json`

```json
{
  "checkpoint": "<path or model ID>",
  "strategy": "tabular | predictions | hf-trainer | lm-evaluation-harness | custom",
  "device": "<device>",
  "dtype": "<dtype>",
  "tasks": ["<task>"],
  "baseline": "<path or null>",
  "results": [
    {
      "task": "<task>",
      "metric": "<metric>",
      "score": 0.7823,
      "ci": [0.751, 0.812],
      "n": 4000,
      "baseline_score": 0.7441,
      "baseline_ci": [0.712, 0.775],
      "delta": 0.0382,
      "delta_ci": [0.012, 0.064],
      "regressed": false
    }
  ],
  "protocol": {"split": "val | test", "final": false, "test_keys_sha256_match": null, "test_evaluations": 0},
  "calibration": {"brier": 0.081, "ece": 0.019},
  "operating_point": {"threshold": 0.32, "precision": 0.58, "recall": 0.63, "flagged_rate": 0.004},
  "slices": [
    {"col": "<column>", "value": "<value>", "n": 412, "point": 0.71, "ci": [0.64, 0.78], "flagged": false}
  ],
  "eval_metrics_path": "<out-dir>/eval-metrics-val.json",
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
    {"pattern": "<description>", "severity": "blocker | high | medium | low", "action": "<text>"}
  ],
  "model_card_path": "<out-dir>/MODEL_CARD.md",
  "caveats": ["<caveat>"]
}
```

---

### `train-model`

Written to: `<out-dir>/train-model.json`

```json
{
  "train_cmd": "<exact command executed>",
  "hyperparameters": {"lr": 1e-4, "batch_size": 32},
  "early_stopping": {
    "enabled": true,
    "native": true,
    "metric": "eval_loss",
    "patience": 5,
    "triggered": false,
    "triggered_at_step": null
  },
  "terminal_state": "SUCCEEDED | FAILED | EARLY_STOPPED | CANCELLED | TIMEOUT",
  "total_steps": 5000,
  "total_epochs": 3,
  "final_metrics": {"eval_loss": 0.312, "eval_f1": 0.891},
  "best_checkpoint": "<path or null>",
  "all_checkpoints": [
    {"path": "<path>", "step": 1000, "metrics": {"eval_loss": 0.420}}
  ],
  "training_duration_seconds": 6180,
  "babysit_training_ref": "<out-dir>/babysit-training.json",
  "seed": 42,
  "preflight": [
    {"check": "init-loss | overfit-one-batch | save-resume | sample-fit | non-constant-predictions | feature-count | too-good-to-be-true", "result": "pass | fail | skipped", "detail": "<text>"}
  ],
  "sweep": {"trials": 40, "best_value": 0.812, "best_params": {"<param>": "<value>"}, "objective": "val | cv"},
  "provenance_path": "<out-dir>/provenance-train.json",
  "tracking_url": "<MLflow/W&B run URL or null>"
}
```

---

### `demonstrate-value`

Written to: `<out-dir>/demonstrate-value.json`

```json
{
  "model": "<path or null>",
  "business_context": "<plain-language description>",
  "primary_metric": "<metric name>",
  "baseline_score": 0.612,
  "model_score": 0.847,
  "improvement_delta": 0.235,
  "business_impact": [
    {
      "metric": "<metric name>",
      "description": "<plain-language impact>",
      "estimated_value": "<text or null>"
    }
  ],
  "presentation_path": "<out-dir>/value-demo.html",
  "evidence_verified": true,
  "assumptions": [
    {"input": "<name>", "value": "<value>", "source": "user-provided | assumed"}
  ],
  "presentation_sections": ["Problem", "Baseline", "Model Performance", "Key Drivers", "Business Impact", "Risks and Caveats", "Recommendation"],
  "showboat_version": "<version or null>",
  "inputs_used": {
    "eval_results": "<path or null>",
    "explain_results": "<path or null>",
    "baseline_results": "<path or null>"
  }
}
```

---

### `build-review-page`

Written to: `<out-dir>/build-review-page.json`

```json
{
  "gate": "<gate number under review, or null>",
  "pages": [
    {
      "page": "decision | label | split | baseline | errors | value | tried",
      "path": "<out-dir>/review/<page>.html",
      "sha256": "<sha256 of the page>",
      "sources": ["check-eval.json", "build-baseline.json"],
      "check": {"ok": true, "words": 211, "refs_checked": 19, "refs_existence_only": 1, "literals": 0, "unbound_numbers": 0},
      "browser_verified": true
    }
  ],
  "omitted": [{"page": "<page>", "reason": "<missing artifact or field, and the skill that would produce it>"}],
  "entry_page": "<out-dir>/review/decision.html",
  "responses_path": "<out-dir>/review/responses.jsonl"
}
```

`decision` describes the pages, not the model: `GO` when every requested page passed `check_page.py --strict`, `CONDITIONAL` when a page was omitted, `NO-GO` when a page failed and must not be shown. `provenance` is omitted.

Each page binds the values it shows to artifact fields with `data-ref="<file>#<JSON pointer>"` and carries the sha256 of every artifact it read in a `<script type="application/json" id="review-sources">` block, so a page that disagrees with its artifacts, or is older than them, fails the check.

Reviewer replies are appended to `<out-dir>/review/responses.jsonl`, one JSON object per line:

```json
{"page": "<page>", "claim": "<tag on the page, e.g. B2>", "verdict": "accepted | changes-requested | rejected", "comment": "<the reviewer's words>", "reviewer": "<name>", "at": "<ISO-8601 UTC>", "page_sha256": "<sha256 of the page they read>"}
```

---

### `recommend-new-approaches`

Written to: `<out-dir>/recommend-new-approaches.json`

```json
{
  "model": "<path or null>",
  "task_type": "classification | regression | ranking | forecasting",
  "primary_metric": "<metric name>",
  "current_score": 0.891,
  "baseline_score": 0.712,
  "performance_gap": "<text describing gap to target or ideal>",
  "diagnostic_summary": "<2-3 sentence summary of key weaknesses>",
  "recommendations": [
    {
      "rank": 1,
      "idea": "<short title>",
      "rationale": "<grounded in artifact signals>",
      "category": "architecture | loss | data | training | regularization | other",
      "expected_impact": "high | medium | low",
      "effort": "high | medium | low",
      "next_command": "<concrete CLI command or code change, or null>",
      "source": "artifact-analysis | literature | autoresearch"
    }
  ],
  "autoresearch_used": false,
  "autoresearch_path": "<out-dir>/autoresearch/program.md or null",
  "artifacts_used": ["<path1>", "<path2>"]
}
```

---

### `select-approach`

Written to: `<out-dir>/select-approach.json`

```json
{
  "problem_type": "<plain-language description>",
  "recommended_approach": "no-ml | supervised | forecasting | unsupervised | embeddings | llm-prompting | llm-fine-tuning | preference-rl-tuning | agent",
  "candidates": [
    {
      "approach": "<approach ID>",
      "fit": "high | medium | low",
      "rationale": "<why>",
      "data_needed": "<what data and whether it exists>",
      "eval_method": "<how it will be evaluated>",
      "est_cost": "<build and run cost>",
      "risks": ["<risk>"]
    }
  ],
  "ruled_out": [{"approach": "<approach ID>", "reason": "<why>"}],
  "constraints": {
    "labels_available": "<description>",
    "data_volume": "<description>",
    "latency": "<description>",
    "explainability": "<description>",
    "data_egress_allowed": true,
    "compute": "<description>"
  },
  "what_would_change_this": ["<evidence that would flip the recommendation>"],
  "lifecycle_map": {
    "applies": ["<skill>"],
    "skipped": [{"skill": "<skill>", "reason": "<why>"}],
    "not_covered": ["<capability the plugin does not provide for this approach>"]
  }
}
```

---

### `check-deployment-readiness`

Written to: `<out-dir>/check-deployment-readiness.json`

```json
{
  "model_path": "<path>",
  "package_format": "joblib | mlflow | onnx | hf | hosted",
  "signature_path": "<out-dir>/model/signature.json",
  "serving_mode": "batch | online",
  "parity": {"n": 1000, "max_abs_diff": 0.0, "n_mismatch": 0, "parity_pass": true},
  "latency": {"p50_ms": 1.2, "p95_ms": 2.0, "p99_ms": 3.1, "budget_ms": 50, "pass": true},
  "throughput_rows_per_s": 50000,
  "model_size_mb": 3.2,
  "peak_rss_mb": 410,
  "contract_check": {"violations": 0, "blockers": 0},
  "drift_baseline_path": "<out-dir>/training-profile.json",
  "monitoring_plan_path": "<out-dir>/monitoring-plan.md",
  "rollout": {"strategy": "shadow -> canary -> full", "rollback_criteria": "<text>"}
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
  "level": "junior | senior | staff",
  "autonomy": "review-every-gate | review-key-gates | autonomous",
  "approach": "<approach ID>",
  "gates": [
    {
      "gate_number": "0-10, or \"4b\"",
      "gate_name": "select-approach | review-target | check-dataset-quality | build-baseline | plan-experiment | feature-engineer | check-data-pipeline | train-model | babysit-training | check-failed-run | check-eval | explain-model | check-deployment-readiness | demonstrate-value | recommend-new-approaches | build-review-page",
      "status": "PASS | FAIL | SKIPPED | PENDING",
      "artifact_path": "<out-dir>/<skill-name>.json",
      "timestamp": "<ISO-8601>",
      "decision": "GO | NO-GO | CONDITIONAL"
    }
  ],
  "final_test": {"metric": "<metric>", "point": 0.79, "ci": [0.75, 0.83], "delta": 0.11, "delta_ci": [0.07, 0.15], "test_keys_sha256_match": true},
  "evidence": {"notebook": "<out-dir>/evidence.md", "blocks": 24, "verified": true, "verified_at": "<ISO-8601>", "changed_blocks": 0, "log": "<out-dir>/evidence-verify.txt"},
  "signed_off_by": "<user>",
  "signed_off_at": "<ISO-8601>",
  "ml_test_score": {
    "data": 2.5, "model": 3.0, "infra": 2.0, "monitoring": 1.5, "final": 1.5,
    "items": [{"section": "data | model | infra | monitoring", "test": "<id and name>", "points": 0.5, "evidence": "<path, or planned/not assessed>"}]
  },
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
  "selected_scenario": "hard-fraud | hard-readmission | xhard-churn",
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
