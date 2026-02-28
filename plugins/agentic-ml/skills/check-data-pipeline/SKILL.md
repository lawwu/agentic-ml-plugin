---
name: check-data-pipeline
description: Dry-run a preprocessing pipeline on a small sample to catch shape, dtype, value range, padding, special token, label encoding, and collation issues before full training. Writes inline validation code tailored to your pipeline. Invoke this automatically whenever someone is about to start a training run, has changed their dataset or model, or mentions tokenization, padding, shape errors, or collation problems — even if they don't explicitly ask for pipeline validation. Shape/dtype mismatches and label shifts are the most common silent failures in ML pipelines and should always be caught before committing to a full run.
argument-hint: "[pipeline-script | notebook | --framework hf|torch|tf|jax] [--model MODEL_NAME_OR_PATH] [--sample N] [--task classification|regression|language-modeling|seq2seq|token-classification]"
---

# Check Data Pipeline

Dry-run your data preprocessing pipeline on a small sample and validate every output property before committing to a full training run.

## Invocation

Arguments (`$ARGUMENTS`) are interpreted as:

- `path/to/preprocess.py` — data preprocessing script to inspect and instrument
- `path/to/notebook.ipynb` — notebook containing pipeline code
- `--framework hf|torch|tf|jax` — framework driving the pipeline
- `--model MODEL` — model name or path (used to load tokenizer for token-level checks)
- `--sample N` — number of examples to run through (default: 32)
- `--task` — task type to select appropriate validation targets

Target: `$ARGUMENTS`

## Your responsibilities

### 1. Understand the pipeline

Read the provided script or notebook. Identify:

- Data source and loading mechanism
- Preprocessing steps (tokenization, normalization, augmentation, feature extraction)
- Output collation (DataCollator, custom collate_fn, tf.data batching)
- Framework and model type

If no script is provided, ask the user to describe or paste the core preprocessing code before proceeding.

### 2. Write inline validation code

Write a short validation script (< 100 lines) that:

1. Loads `--sample N` raw examples
2. Runs them through the full pipeline
3. Inspects and asserts every output property from [references/pipeline-checks.md](references/pipeline-checks.md)

Do not use off-the-shelf profiling libraries — write targeted assertions that match the specific pipeline. Tailor the checks to the `--task` and `--framework`.

See code templates in [references/framework-patterns.md](references/framework-patterns.md).

### 3. Run the validation

Execute the validation script and capture its output. If a check fails, capture the exact failing value and the assertion that triggered it.

Do not proceed past a check failure silently — report each failure immediately.

### 4. Checks to perform

See [references/pipeline-checks.md](references/pipeline-checks.md) for full specs. Core checks:

**Shape and type**
- `input_ids`: shape `(batch, seq_len)`, dtype `int64` (or int32 for TF/JAX)
- `attention_mask`: same shape as `input_ids`, values in `{0, 1}`
- `labels`: shape matches task expectation; correct dtype for loss function
- No `None` dimensions in static shapes (TF/JAX)

**Value ranges**
- `input_ids` values in `[0, vocab_size)` — no out-of-range token IDs
- `attention_mask` is binary (no float leak)
- `labels` for classification: values in `[0, num_classes)` or `-100` for ignored positions
- `labels` for regression: no NaN/Inf, within expected range
- Pixel values (vision): in expected range `[0, 1]` or `[0, 255]` depending on normalization

**Padding and truncation**
- Sequences padded to consistent length within a batch
- Padding token ID matches `tokenizer.pad_token_id`
- `attention_mask` is `0` on padding positions
- No sequences that are entirely padding (empty input)
- Truncation preserves meaningful content (check first/last token)

**Special tokens**
- `[CLS]`/`[SEP]` or `<s>`/`</s>` present where expected
- `[BOS]`/`[EOS]` in generation tasks
- No special tokens in label sequences for causal LM (or correctly shifted)
- Decoder input IDs start with `decoder_start_token_id` for seq2seq

**Label encoding**
- Classification: labels are integers, not strings; no label `-1` (use `-100` for ignored)
- Token classification: label length matches `input_ids` length
- Seq2seq: labels are shifted correctly; `PAD` positions masked with `-100`
- Regression: labels are float32 scalars

**Collation**
- All tensors in a batch have consistent shape (no ragged without explicit support)
- `DataLoader` with `num_workers > 0` produces deterministic output for the same seed
- No Python objects (lists, dicts) leaking into the batch (would break distributed)

### 5. Report format

```text
Pipeline Validation Report
==========================
Framework: <framework>
Model: <model>
Sample size: <N> examples → <N> batches (batch_size=<B>)
Task: <task>

Checks passed: <N>/<total>

Failures:
1) <check name>: <expected> vs <actual>
   Location: <step in pipeline where it occurs>
   Fix: <concrete code change>

Warnings:
1) <check name>: <observation> (not a hard failure but worth investigating)

All-clear checks: input_ids shape, attention_mask values, ...

Next steps:
- <action to fix failure 1>
- <action to validate fix>

Decision: GO | NO-GO
Confidence: high|medium|low
```

### JSON artifact

Write `check-data-pipeline.json` to `--out-dir` (or `./` if invoked standalone) following the schema in [../../references/schemas.md](../../references/schemas.md). Use vocabulary from [../../references/vocabulary.md](../../references/vocabulary.md).

Key fields to populate:
- `decision`: `GO` when all checks pass; `NO-GO` when any failure exists
- `checks_passed`, `checks_total`, `failures`, `warnings`
- `findings`: one entry per failure (severity `blocker`) and warning (severity `medium`)

If all checks pass:

```text
Pipeline Validation Report
==========================
All <N> checks passed on <N> examples.
Pipeline is ready for full training run.

Decision: GO
Confidence: high
```

### 6. Fix policy

You may write and run validation code freely — it is read-only with respect to the training pipeline.

Require user approval before:

- Modifying the user's preprocessing script or notebook
- Changing tokenizer settings or model configuration
- Changing batch size, sequence length, or padding strategy

Always show the exact code change before applying it.

### 7. Stop conditions

Stop when:

- All checks pass and pipeline is declared ready
- All failures are reported with concrete fixes and the user must apply them
- The pipeline cannot be run (missing dependency, import error) and the blocker is clearly stated

## Quick heuristics

- Shifted label issues → the most common seq2seq/causal-LM mistake; always verify `labels[i] = input_ids[i+1]`
- `attention_mask` all ones → padding is disabled or pad_token_id equals a real token
- `labels` containing `tokenizer.pad_token_id` (not `-100`) → loss computed on padding, inflating validation loss
- Out-of-range `input_ids` → added special tokens not in the original vocab; call `tokenizer.add_special_tokens` and `model.resize_token_embeddings`
- Empty `attention_mask` (all zeros) → truncated to length 0 or padding bug; check `max_length` and `truncation=True`
- Non-deterministic DataLoader output → missing `worker_init_fn` and `generator` seed; can cause subtle training instability

## Example

```text
/ml-skills:check-data-pipeline preprocess.py --framework hf --model bert-base-uncased --sample 64 --task classification

Pipeline Validation Report
==========================
Framework: HuggingFace Transformers
Model: bert-base-uncased (vocab_size=30,522)
Sample size: 64 examples → 4 batches (batch_size=16)
Task: classification

Checks passed: 11/13

Failures:
1) labels dtype: expected int64, got float32
   Location: dataset.map() lambda — line 42 of preprocess.py
   Fix: cast label to int in map: lambda x: {"label": int(x["label"])}

2) attention_mask values: found value 2 in batch 3 (expected {0, 1})
   Location: custom_collate_fn — line 87
   Fix: attention_mask is being summed instead of unioned; use torch.clamp(mask, 0, 1)

Next steps:
- Fix label dtype cast in preprocess.py:42
- Fix collate_fn attention_mask logic in preprocess.py:87
- Re-run: /ml-skills:check-data-pipeline preprocess.py --framework hf --model bert-base-uncased --sample 64 --task classification
```

## Additional resources

- [references/pipeline-checks.md](references/pipeline-checks.md) — Full check specifications with expected values by task and model type
- [references/framework-patterns.md](references/framework-patterns.md) — Code templates for HF datasets.map, PyTorch DataLoader, tokenizer configs, and collators
