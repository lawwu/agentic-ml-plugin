# Approach Guide

How to choose between kinds of ML/AI, cheapest-first. Each section gives:

- when it fits
- what data it needs
- how to evaluate it
- the main risks
- which plugin skills apply

Approach IDs match [vocabulary.md](../../../references/vocabulary.md#approach).

## Decision order

Work down this list and stop at the first approach that can plausibly meet the bar. Prefer the simpler option when two fit — it is cheaper to build, explain, and maintain.

1. **`no-ml`** — Can a rule, heuristic, SQL query, or dashboard meet the bar? Is there no data yet? Then ship that and measure it (Rule 1 of the Rules of ML).
2. **Structured/tabular data with a labeled outcome** → `supervised` (gradient-boosted trees first). Do not use an LLM for tabular prediction.
3. **Future values of a time series** → `forecasting`. Start with statistical and zero-shot foundation-model baselines; train a custom model only if they miss the bar.
4. **No labels, and the goal is to find structure or outliers** → `unsupervised`. First ask whether labeling a few hundred examples would turn it into a `supervised` problem with a measurable target.
5. **Find similar items, search, deduplicate, or route text/images** → `embeddings` (plus a vector index). Add a reranker only if retrieval quality misses the bar.
6. **Classify, extract, summarize, or generate text** → `llm-prompting` first (zero/few-shot, structured outputs) against a labeled eval set of 50–200 examples. Then:
   - If missing knowledge is the gap → add retrieval (RAG) with `embeddings`.
   - If cost, latency, volume, or consistency is the gap, and you have hundreds to thousands of good examples → `llm-fine-tuning` (LoRA, or distill into a smaller model).
   - For high-volume classification with plenty of labels → `supervised` on embeddings, or a fine-tuned small encoder.
   - Do not fine-tune to add knowledge; use retrieval.
7. **`preference-rl-tuning`** — only when all of these hold:
   - prompting and supervised fine-tuning have plateaued
   - you have preference pairs (DPO-style) or a verifiable reward (RLVR: unit tests, exact-match answers, checkers)
   - you can detect reward hacking

   This is the highest cost and risk.
8. **`agent`** — only when the task needs multiple steps with tools or actions on external systems and cannot be done in one call:
   - Start with a fixed workflow (one LLM call plus tools) before an autonomous loop.
   - Irreversible actions need guardrails and human approval.

## Questions to answer first

1. **Decision:** What decision or action will the output drive? How often (batch, real-time)? What does a wrong answer cost?
2. **Input:** tabular, time series, text, images, mixed, or a multi-step task in an environment?
3. **Output:** a number or class, a ranking, future values, groups or anomalies, similar items, generated text or structured fields, or actions?
4. **Supervision:** Do labeled examples exist, and how many? Can they be made cheaply? Do preference pairs exist? Is there an automatic check for success?
5. **Constraints:**
   - latency and cost per prediction
   - explainability or regulation
   - whether data may leave the network (hosted LLM and forecasting APIs)
   - GPUs
   - team skills and who maintains it
6. **Bar:** What score or behavior would make this worth shipping? Who decides?

If 1, 3, or 4 cannot be answered, return `NO-GO` and ask — do not guess.

## Approaches

### `no-ml`

- **Fits:** clear business rules; small or no data; the cost of errors is low; explainability is paramount.
- **Evaluate:** measure the rule on historical data with `build-baseline`; it becomes the bar any later ML must beat.
- **Risks:** rules rot silently; schedule a review.
- **Plugin:** `review-target` → `check-dataset-quality` → `build-baseline`, then stop.

### `supervised`

- **Fits:** a labeled outcome on tabular data (classification, regression, ranking); also text or images with plenty of labels.
- **Data:** hundreds to millions of labeled rows. Labels must be available at a known delay after prediction time.
- **Evaluate:** locked test set; metric with confidence intervals vs. baseline; slices; calibration — see [evaluation-protocol.md](../../../references/evaluation-protocol.md).
- **Risks:** leakage, label definition drift, training/serving skew.
- **Plugin:** full lifecycle; tabular track in `check-data-pipeline`, `train-model` (`train_tabular.py`), `check-eval`.

### `forecasting`

- **Fits:** predicting future values of one or many time series.
- **Data:** history covering several seasonal cycles; known future covariates (holidays, promotions) if used.
- **Baselines, in order:**
  1. naive and seasonal-naive
  2. statistical (ETS, ARIMA, Theta — e.g. `statsforecast`)
  3. zero-shot time-series foundation model — e.g. Amazon Chronos / Chronos-Bolt, Google TimesFM, Salesforce Moirai. These forecast without training on your data.

  A custom model must beat all of them to be worth maintaining. Hosted forecasting APIs (e.g. Nixtla TimeGPT) send data off-network; check `data_egress_allowed` first. Check model licenses before production use.
- **Evaluate:**
  - rolling-origin backtest (several forecast origins, fixed horizon), never a random split
  - scale-free error (MASE, sMAPE)
  - quantile loss or coverage for probabilistic forecasts
- **Risks:** leakage through features only known after the forecast date; level shifts; aggregation mismatch between training and decision.
- **Plugin:** full lifecycle; `build-baseline` runs the statistical and foundation-model baselines; `review-target` defines horizon and backtest windows.

### `unsupervised`

- **Fits:** segmentation, anomaly detection, exploratory structure, dimensionality reduction.
- **Evaluate:** there is no ground truth, so pick a proxy up front:
  - stability across resamples and seeds
  - silhouette or similar for clusters
  - precision of the top-k anomalies under human review
  - a downstream business metric
- **Risks:** results that look meaningful but aren't; no way to say "better". Often a few hundred labels would turn this into a supervised problem.
- **Plugin:** `review-target` (define the use and the proxy metric), `check-dataset-quality`, `build-baseline` (z-score/IQR rules for anomalies; simple segment rules), `train-model`, `check-deployment-readiness`.
- **Not covered:** unsupervised metrics in `eval_report.py`; compute them in a custom eval script.

### `embeddings`

- **Fits:** semantic search, retrieval for RAG, deduplication, clustering text or images, recommendations from content, classification via a linear probe on embeddings.
- **Data:** the corpus, plus a labeled set of queries with relevant items (50–500 queries) to evaluate.
- **Baseline:** keyword search (BM25) — often hard to beat on exact-match queries.
- **Evaluate:** recall@k, nDCG@k, MRR on the labeled query set; latency and index size.
- **Risks:**
  - domain mismatch of off-the-shelf embedding models
  - stale indexes
  - sending documents to a hosted embedding API when data must stay in-network
- **Plugin:** `review-target` (queries and relevance definition), `check-dataset-quality` (corpus duplicates, empty docs, PII), `build-baseline` (BM25), `plan-experiment` (models to compare), `check-eval` (custom script), `check-deployment-readiness`. Skip `train-model` unless fine-tuning the embedding model.
- **Not covered:** a bundled retrieval-metrics script.

### `llm-prompting`

Off-the-shelf LLM, optionally with retrieval (RAG).

- **Fits:** classification, extraction, summarization, or generation where a capable model plus instructions and examples gets close to the bar; low to moderate volume.
- **Data:** a labeled eval set (50–200 examples to start, covering edge cases), and the knowledge sources for RAG.
- **Baseline:** rules or keyword matching for classification and extraction; the current human process for generation.
- **Evaluate:**
  - exact match or field-level F1 for extraction
  - accuracy or F1 for classification
  - a rubric graded by humans or an LLM judge for generation — validate the judge against human labels first
  - also cost and latency per call
- **Risks:** prompt brittleness across model versions; hallucination; data egress to hosted models; unbounded cost at volume.
- **Plugin:** `review-target`, `check-dataset-quality` (eval-set quality), `build-baseline`, `check-eval` (custom eval script), `check-deployment-readiness` (latency, cost, data egress). Skip `train-model`, `babysit-training`, `explain-model`; replace `explain-model` with error analysis on failures.
- **Not covered:** LLM-judge calibration and prompt versioning.

### `llm-fine-tuning`

SFT, LoRA/QLoRA, distillation.

- **Fits:** prompting works but is too expensive, slow, or inconsistent at volume; or a specific format or behavior must be reliable. Not for adding knowledge.
- **Data:** hundreds to tens of thousands of high-quality input→output examples, deduplicated and free of eval-set overlap.
- **Baseline:** the prompted base model (and the prompted larger model) on the same eval set.
- **Evaluate:**
  - task eval set (held out, contamination-checked)
  - regression checks on general capability (`lm-evaluation-harness`)
  - cost and latency vs. the prompted baseline
- **Risks:** catastrophic forgetting; train/eval contamination; chat-template and loss-masking bugs; license terms of the base model.
- **Plugin:** full lifecycle; `check-data-pipeline` (tokenization, chat template, label masking), `train-model`, `babysit-training`, `check-eval` (harness plus custom). Replace `explain-model` with error analysis.

### `preference-rl-tuning`

RLHF, DPO, RLVR.

- **Fits:** after SFT has plateaued, when quality is defined by preferences (DPO/RLHF) or by an automatic verifier (RLVR: unit tests pass, answer matches, checker accepts).
- **Data:** preference pairs, or a verifier plus a prompt set; a held-out eval that the reward cannot game.
- **Baseline:** the SFT model.
- **Evaluate:**
  - held-out task success
  - human preference win rate
  - reward-hacking probes (reward up while held-out quality is flat or down)
  - KL divergence from the reference model
- **Risks:** reward hacking; instability; high compute; verifier bugs that silently reward wrong answers.
- **Plugin:** as `llm-fine-tuning`; `babysit-training` can watch reward and KL if logged.
- **Not covered:** reward-model and verifier validation, reward-hacking checks.

### `agent`

LLM with tools, multi-step.

- **Fits:** the task needs several steps, tool use, or actions in external systems (search, code execution, APIs), and the path varies by input.
- **Data:** a task suite with success criteria (20–100 tasks to start), plus a sandbox or mocks for tools.
- **Baseline:** a single LLM call without tools, a fixed workflow, or the current human process.
- **Evaluate:** task success rate, cost and latency per task, the number of steps, and the safety of actions taken. Review trajectories, not just final answers.
- **Risks:** compounding errors; runaway cost; irreversible actions; prompt injection through tool outputs.
- **Plugin:** `review-target` (task and success definition), `build-baseline`, `check-eval` (custom task-suite script), `check-deployment-readiness` (permissions, cost, latency).
- **Not covered:** trajectory evaluation and tool-permission review.

## Lifecycle map

`select-approach` writes `lifecycle_map` from the plugin coverage above:

- `applies`: skills to run, in order
- `skipped`: skills that do not apply, each with the reason
- `not_covered`: capabilities this approach needs that the plugin does not provide yet. Name them so the user can fill the gap deliberately.

`orchestrate-e2e` follows the map: gates in `skipped` are recorded as `SKIPPED` with the reason.
