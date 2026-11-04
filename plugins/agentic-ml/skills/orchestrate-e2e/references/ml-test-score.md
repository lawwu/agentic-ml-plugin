# ML Test Score

Score each run against **"The ML Test Score: A Rubric for ML Production Readiness and Technical Debt Reduction"** (Breck, Cai, Nielsen, Salib, Sculley — Google, IEEE Big Data 2017). The rubric has 28 tests in four sections.

## Scoring

Per test:

| Points | Meaning |
|---|---|
| 0 | Not done, or no evidence |
| 0.5 | Done manually, with results documented — in this run, an artifact path |
| 1 | Automated and run repeatedly (in CI, the training pipeline, or production) — only with evidence of that automation in the user's repository or infrastructure |

- Each section score is the sum of its 7 tests.
- **The final score is the lowest of the four section scores.** A system is only as production-ready as its weakest area.

Rules:

- Award points only with an evidence path (an artifact, a file, a CI config). No evidence means 0.
- A single orchestrated run does work once, so most tests earn at most 0.5. Never award 1 for something done only in this run.
- Plans (monitoring, rollout, rollback) earn 0 until they are implemented. Record them as `planned` in the evidence text.
- Tests the run did not assess score 0 with the note `not assessed`.

Interpretation of the final score (from the paper):

| Final score | Meaning |
|---|---|
| 0 | More of a research project than a productionized system |
| (0, 1] | Not totally untested, but there may be serious holes in reliability |
| (1, 2] | A first pass at basic productionization; more investment needed |
| (2, 3] | Reasonably tested; more could be automated |
| (3, 5] | Strong automated testing and monitoring, appropriate for mission-critical systems |
| > 5 | Exceptional automated testing and monitoring |

A typical single run lands at or below 2, limited by the monitoring section. That is expected. Present it as the gap between "validated offline" and "operated in production", not as a failure.

## Mapping to gates and artifacts

### Data

| # | Test | Evidence in this plugin |
|---|---|---|
| D1 | Feature expectations are captured in a schema | `data-contract.json` (`check-dataset-quality`) |
| D2 | All features are beneficial | `explain-model` importance, or an ablation; flag features with ~0 importance |
| D3 | No feature's cost is too much | per-feature cost or latency noted in `feature-engineer` or `check-deployment-readiness`; usually not assessed |
| D4 | Features adhere to meta-level requirements | blocked features in `feature-engineer`; personal-data checks in `check-dataset-quality` |
| D5 | The data pipeline has appropriate privacy controls | personal-data findings resolved; data-egress decision recorded in `select-approach` |
| D6 | New features can be added quickly | not assessable from one run; 0 unless the pipeline is code with tests |
| D7 | All input feature code is tested | `check-data-pipeline` validation (0.5); unit tests in the repo (1) |

### Model

| # | Test | Evidence in this plugin |
|---|---|---|
| M1 | Model specs are reviewed and submitted | training code and `train-config.json` in version control (provenance shows a clean git state) |
| M2 | Offline and online metrics correlate | needs production data; 0 (`planned` via canary in the monitoring plan) |
| M3 | All hyperparameters have been tuned | `train-model` sweep results |
| M4 | The impact of model staleness is known | evaluation by time period on a time split (e.g. per-quarter `val` metrics) |
| M5 | A simpler model is not better | `build-baseline` plus `check-eval` paired delta with interval |
| M6 | Model quality is sufficient on all important data slices | `check-eval` slices with intervals |
| M7 | The model has been tested for considerations of inclusion | `explain-model` bias audit |

### ML infrastructure

| # | Test | Evidence in this plugin |
|---|---|---|
| I1 | Training is reproducible | provenance (git SHA, lockfiles, data hash, seed), plus an evidence-notebook block that retrains and reproduces the metrics; 1 only if retraining is checked automatically (e.g. `showboat verify` in CI) |
| I2 | Model specs are unit tested | `train-model` pre-flight checks (0.5); unit tests in the repo (1) |
| I3 | The ML pipeline is integration tested | this end-to-end run completed on real data (0.5); an automated pipeline test (1) |
| I4 | Model quality is validated before attempting to serve it | `check-eval --final`, a verified evidence notebook, and the gate 10 decision |
| I5 | The model allows debugging by observing step-by-step computation on a single example | `explain-model` per-example explanations, and `serving_check.py` scoring single rows |
| I6 | Models are canaried before serving | 0 (`planned` in the rollout plan) |
| I7 | Serving models can be rolled back | 0 until a rollback has been exercised (`planned` in the rollback plan) |

### Monitoring

| # | Test | Evidence in this plugin |
|---|---|---|
| N1 | Dependency changes result in notification | lockfile hashes in provenance are not notifications; 0 unless the repo has alerts (e.g. Dependabot) |
| N2 | Data invariants hold in training and serving inputs | `data_contract.py validate` on `val` (0.5 pre-deployment); in production (1) |
| N3 | Training and serving are not skewed | `serving_check.py` parity (0.5 pre-deployment); production skew monitoring (1) |
| N4 | Models are not too stale | 0 (`planned` staleness alert) |
| N5 | Models are numerically stable | `babysit-training` NaN/Inf checks and pre-flight (0.5) |
| N6 | Computing performance has not regressed | `serving_check.py` latency vs. budget (0.5 pre-deployment) |
| N7 | Prediction quality has not regressed on served data | 0 (`planned` delayed-label monitoring) |

## Output

Write to `run-summary.json`:

```json
"ml_test_score": {
  "data": 2.5,
  "model": 3.0,
  "infra": 2.0,
  "monitoring": 1.5,
  "final": 1.5,
  "items": [
    {"section": "data", "test": "D1 Feature expectations are captured in a schema", "points": 0.5, "evidence": "<out-dir>/data-contract.json"},
    {"section": "monitoring", "test": "N4 Models are not too stale", "points": 0, "evidence": "planned: monitoring-plan.md staleness alert"}
  ]
}
```

List all 28 items. In the summary, name the 2–3 lowest-scoring tests and what would move them, e.g. "N2 → 1: run `data_contract.py validate` on every production batch".
