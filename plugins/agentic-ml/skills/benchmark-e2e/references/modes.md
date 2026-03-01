# Modes

Use consistent execution definitions so benchmark cells are comparable.

## Shared lifecycle framework

Every mode must attempt the same 9 lifecycle stages in order, regardless of mode. This is what makes cells comparable. Record each stage's outcome — do not skip stages for any reason other than an upstream hard dependency (e.g., skip stage 6 if no training run was produced by stage 2/3/4/5).

| Stage | Lifecycle gate | `no-plugin` activity | `plugin` activity | `automl` activity |
|---|---|---|---|---|
| 1 | Target readiness | Manual target framing and metric definition | `review-target` | Define target/task in code |
| 2 | Experiment plan | Manual model selection and HP search plan | `plan-experiment` | AutoGluon hyperparameter space (automatic) |
| 3 | Non-ML baseline | Manual heuristic baseline | `build-baseline` | Manual heuristic baseline |
| 4 | Dataset quality | Manual dataset checks and EDA | `check-dataset-quality` | Manual schema/label inspection |
| 5 | Data pipeline | Manual preprocessing sanity checks | `check-data-pipeline` | AutoGluon pipeline dry-run |
| 6 | Training stability | Manual training run and log monitoring | `babysit-training` (+ `check-failed-run` on failure) | AutoGluon `fit()` with runtime logging |
| 7 | Evaluation quality | Manual metric computation and baseline comparison | `check-eval` | AutoGluon leaderboard + holdout metrics |
| 8 | Interpretability/bias | Manual feature importance and bias review | `explain-model` | AutoGluon feature importance + bias check |
| 9 | Promotion decision | Manual summary decision | Final `GO`/`NO-GO` from `orchestrate-e2e` | Deployment-readiness recommendation |

**A NO-GO at any stage does not halt the benchmark.** Record the NO-GO decision and continue measuring remaining stages. The benchmark needs full coverage to score reliability; stopping early would make scores incomparable across modes.

## Python execution requirements (all modes)

Use `uv` for all Python operations across every mode:

- create virtual environments: `uv venv`
- install packages: `uv pip install <pkg>` or `uv add <pkg>`
- run scripts: `uv run <script.py>`
- run inline/ad-hoc code: `uv run python -c "..."`

Never use `python`, `python3`, `pip`, or `pip3` directly. Never use `venv`, `virtualenv`, or `conda`.

## Telemetry capture expectations

For every mode run, capture:

- `loc_run`: executed code lines (scripts/notebooks/inline blocks; exclude blank and comment-only lines)
- `tokens_in`, `tokens_out`, `tokens_total`

Preferred token source order:

1) runtime/API usage metadata from the mode
2) provider usage logs tied to the run ID
3) estimator from request/response transcripts (mark as estimated)

If unavailable, record `unknown` and explain why in the run notes.

## no-plugin

Manual/scripted flow without plugin command shortcuts. Do not invoke any skills in this mode.

Execute each of the 9 stages manually. Document decisions, code written, and checks performed for each stage. Record a GO/NO-GO decision per stage based on findings — but always proceed to the next stage regardless of the decision (benchmark does not halt on NO-GO).

## plugin

Flow executed through plugin skills. Invoke each skill individually in stage order — do not use `orchestrate-e2e` as a wrapper, because it halts on NO-GO and would prevent full-coverage measurement. See [skill-matrix.md](skill-matrix.md) for the exact skill invoked per stage.

After each skill completes, record its decision and proceed to the next stage regardless of the result.

## automl (AutoGluon)

AutoML path implemented with AutoGluon. Do not invoke any skills in this mode.

Map AutoGluon's outputs to each of the 9 stages:

- Stages 1–5: perform manually before calling `fit()`; document what was checked
- Stage 5: `TabularPredictor.fit()` (or `MultiModalPredictor` as applicable); capture fit summary and training logs
- Stage 6: extract AutoGluon leaderboard + holdout metrics; compare against baseline
- Stage 7: `predictor.feature_importance()` + manual bias check on protected attributes
- Stage 8: produce deployment-readiness recommendation from AutoGluon artifacts

Execution requirements:

- install dependencies with `uv pip install autogluon`
- run scripts with `uv run ...`

Do not assume AutoGluon internally handles leakage-safe target logic; verify explicitly in stage 1.
