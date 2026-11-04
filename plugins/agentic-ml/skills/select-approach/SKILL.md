---
name: select-approach
description: Helps decide what kind of ML/AI fits a problem before any modeling — no ML (rules), supervised learning, forecasting (including zero-shot time-series foundation models), unsupervised learning, embedding models, prompting an LLM (with or without RAG), LLM fine-tuning, RLHF/DPO/RLVR, or agents. Use at the start of a new ML or AI project, or when someone asks "should we use an LLM for this?", "do we need to fine-tune?", "is this a job for RAG, embeddings, or an agent?", "what kind of model should we build?", or "do we even need ML?". Recommends the cheapest approach likely to meet the bar and maps which lifecycle skills apply.
argument-hint: "<problem description> [--data SOURCE] [--constraints TEXT] [--out-dir DIR] [--run-id ID] [--level junior|senior|staff]"
---

# Select Approach

Recommend the kind of ML/AI that fits the problem — cheapest first — before anyone defines a label or trains a model.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `<problem description>` — the decision or task in plain language
- `--data SOURCE` — optional dataset path, table, or corpus to inspect
- `--constraints TEXT` — latency, cost, explainability, data-egress, compute, or team constraints
- `--out-dir DIR` — output directory (default: `./`)
- `--run-id ID` — run ID shared across orchestrated skills
- `--level` — `junior`, `senior`, or `staff`

Target: `$ARGUMENTS`

## Adapt to the user's level

Resolve the level (`--level`, then `.claude/agentic-ml.local.md`). If neither is set, ask once and offer to save the answer. Follow [../../references/levels.md](../../references/levels.md). Level changes explanation depth, pauses, and how much you build versus review — never the checks, thresholds, or approval rules. Record `level` in the JSON artifact.

- `junior`: recommend one approach, explain it in plain terms, and say what the next skill will do.
- `senior`: top 2–3 candidates with trade-offs and a recommendation.
- `staff`: frame it as a decision — build vs. buy, cost to run and maintain, who owns it, and what evidence would change the call.

## Your responsibilities

### 1. Pin down the problem

Answer the six questions in [references/approach-guide.md](references/approach-guide.md#questions-to-answer-first): decision, input, output, supervision, constraints, and bar.

- Infer what you can from the description and the data. If `--data` is given, look at its shape: tabular, time series, text, images; labels present; row counts; timestamps.
- Ask only for answers you cannot infer. If the decision, the output, or the available supervision is unknown, return `NO-GO` with the questions.

### 2. Walk the decision order

Follow the [decision order](references/approach-guide.md#decision-order) and stop at the first approach that can plausibly meet the bar.

- Always consider `no-ml` first, and say why it does or does not meet the bar.
- For time series, the baselines include statistical models and a zero-shot time-series foundation model before any custom training.
- For text tasks, prompting an off-the-shelf LLM comes before fine-tuning. Fine-tuning comes before preference or RL tuning.
- Agents only when the task truly needs multiple steps with tools.

### 3. Compare candidates

For the recommended approach and up to two alternatives, give:

- fit (`high` / `medium` / `low`)
- data needed and whether it exists
- evaluation method
- rough cost to build and to run
- main risks

List approaches ruled out, with one-line reasons.

### 4. Check constraints

Make each constraint explicit:

- **Data egress:** hosted LLMs, embedding APIs, and forecasting APIs send data off-network. If that is not allowed, recommend self-hosted models or say the approach is blocked.
- **Explainability or regulation:** favor models whose decisions can be explained, or plan the explanation work.
- **Latency and cost per prediction at the expected volume.**
- **Compute:** GPUs needed for fine-tuning and RL; CPU is fine for gradient-boosted trees and zero-shot inference with small models.

### 5. Map the lifecycle

Using the plugin coverage in the guide, write the `lifecycle_map`:

- `applies`: skills to run next, in order
- `skipped`: skills that do not apply, with reasons
- `not_covered`: capabilities this approach needs that the plugin does not provide yet

### 6. Say what would change the recommendation

Name the evidence that would flip the call, e.g.:

- "if the prompted model's F1 on 200 labeled examples is below 0.8, fine-tune"
- "if the zero-shot forecaster's MASE is within 5% of the trained model, keep the zero-shot model"

## Output format

```text
Approach Recommendation
=======================
Problem: <one line>
Decision supported: <what the output drives>
Recommended: <approach> (fit: high|medium|low)
Why: <2–3 sentences>

Candidates:
| Approach | Fit | Data needed | Evaluate with | Cost (build / run) | Main risk |
|----------|-----|-------------|---------------|--------------------|-----------|

Ruled out:
- <approach>: <reason>

Constraints: <egress, latency, explainability, compute>

Next skills: <applies, in order>
Skipped: <skill — reason>
Not covered by the plugin: <list or none>

What would change this: <evidence>

Decision: GO | CONDITIONAL | NO-GO
Confidence: high|medium|low
```

- `GO`: approach chosen with enough information.
- `CONDITIONAL`: approach chosen, but it depends on assumptions that are listed and must be checked (e.g. data egress allowed, label volume).
- `NO-GO`: cannot choose yet; the questions the user must answer are listed.

### Record evidence

Append this skill's section to `<out-dir>/evidence.md` following [../../references/evidence-notebook.md](../../references/evidence-notebook.md): create it with `showboat init` if it does not exist, pass `--workdir <out-dir>`, and keep every `exec` block deterministic, side-effect free, and under about a minute. Set `evidence_notebook` and `evidence_blocks` in the JSON artifact. Record:

- a note with the recommendation, the approaches ruled out, and the assumptions it depends on
- when `--data` is given: an `exec` block printing the facts the recommendation rests on — shape, label presence and rate, and whether timestamps or repeated entities exist

### JSON artifact

Write `select-approach.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md) — `recommended_approach` and every `candidates[].approach` must be an approach ID from the vocabulary.

Key fields to populate:

- `decision`, `recommended_approach`, `problem_type`
- `candidates`, `ruled_out`, `constraints`
- `what_would_change_this`
- `lifecycle_map`: `applies`, `skipped`, `not_covered`
- `findings`: one entry per blocking unknown (`blocker`) or risky assumption (`high`/`medium`)

## Quick heuristics

- Tabular data with a label → gradient-boosted trees; an LLM is the wrong tool
- "We want to use AI" with no decision attached → `NO-GO`; ask what decision changes
- Fewer than ~100 labeled examples → prompting an LLM or labeling more beats training
- "Fine-tune so it knows our documents" → retrieval (RAG), not fine-tuning
- Forecasting with short history or many series → a zero-shot foundation model is a strong baseline; a custom model must beat it
- Exact-match search terms (IDs, codes, names) → keyword search beats embeddings; consider hybrid
- No verifier and no preference data → RLHF/RLVR is not an option yet
- Irreversible actions (payments, emails, deletes) in an agent → require human approval in the design

## Stop conditions

Stop when:

- a recommendation with a lifecycle map is delivered, or
- blocking questions about the decision, the output, or the available supervision are asked.

## Additional resources

- [references/approach-guide.md](references/approach-guide.md) — decision order, per-approach data needs, evaluation, risks, and plugin coverage
