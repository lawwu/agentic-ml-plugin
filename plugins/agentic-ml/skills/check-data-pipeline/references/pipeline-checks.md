# Pipeline Validation Checks

Reference for the `data-pipeline-validate` skill. Full check specifications with expected values by task and model type.

---

## Universal Checks (All Tasks)

### input_ids

| Property | Expected | How to check |
|---|---|---|
| Shape | `(batch_size, seq_len)` | `assert input_ids.ndim == 2` |
| Dtype | `int64` (PyTorch), `int32` (TF/JAX) | `assert input_ids.dtype == torch.long` |
| Range | `[0, vocab_size)` | `assert input_ids.max() < tokenizer.vocab_size` |
| No negatives | All values ≥ 0 | `assert input_ids.min() >= 0` |

### attention_mask

| Property | Expected | How to check |
|---|---|---|
| Shape | Same as `input_ids` | `assert attention_mask.shape == input_ids.shape` |
| Dtype | `int64` or `float32` (both valid) | — |
| Binary values | All in `{0, 1}` | `assert attention_mask.unique().tolist() in [[0], [1], [0, 1]]` |
| Not all zeros | At least one `1` per row | `assert (attention_mask.sum(dim=-1) > 0).all()` |
| Pad positions | `0` where `input_ids == pad_token_id` | cross-check |

### token_type_ids (BERT-style)

| Property | Expected |
|---|---|
| Shape | Same as `input_ids` |
| Values | `{0, 1}` for single/paired sentences |
| Segment boundary | `0` for segment A tokens, `1` for segment B tokens |

---

## Classification Checks

### labels

| Property | Expected | How to check |
|---|---|---|
| Shape | `(batch_size,)` — scalar per example | `assert labels.ndim == 1` |
| Dtype | `int64` | `assert labels.dtype == torch.long` |
| Range | `[0, num_classes)` | `assert labels.max() < num_classes and labels.min() >= 0` |
| No `-1` | Use `-100` for ignore, not `-1` | `assert (labels == -1).sum() == 0` |

**Common failure**: labels are floats from a CSV read without explicit dtype casting.

---

## Token Classification Checks (NER, POS, etc.)

### labels

| Property | Expected | How to check |
|---|---|---|
| Shape | `(batch_size, seq_len)` | `assert labels.shape == input_ids.shape` |
| Dtype | `int64` | `assert labels.dtype == torch.long` |
| Range | `[0, num_labels)` or `-100` | `assert ((labels >= 0) & (labels < num_labels) \| (labels == -100)).all()` |
| Subword alignment | Non-first subword tokens use `-100` | verify with tokenizer word_ids() |
| Special token labels | `[CLS]`, `[SEP]`, `[PAD]` → `-100` | spot check |

**Common failure**: labels for subword tokens not masked with `-100`, causing loss on non-first subword pieces.

---

## Language Modeling Checks (Causal LM)

### input_ids and labels

| Property | Expected |
|---|---|
| Shapes | Both `(batch_size, seq_len)` |
| Label shift | `labels[i] = input_ids[i+1]` for next-token prediction |
| Last token label | `-100` (masked; no next token available) |
| EOS handling | EOS token present and labeled (not masked) |

**Check**:
```python
# Verify label shift
assert (labels[:, :-1] == input_ids[:, 1:]).all(), "Labels are not shifted input_ids"
# Verify last position is masked
assert (labels[:, -1] == -100).all(), "Last label position must be -100"
```

**Common failure**: labels are identical to input_ids (no shift), causing the model to learn to copy the previous token.

---

## Seq2Seq / Encoder-Decoder Checks

### decoder_input_ids

| Property | Expected |
|---|---|
| Shape | `(batch_size, decoder_seq_len)` |
| First token | `decoder_start_token_id` (often `pad_token_id` for T5/mBART) |
| Shift | `decoder_input_ids[:, 1:] == labels[:, :-1]` (teacher forcing) |

### labels

| Property | Expected |
|---|---|
| Padding | `-100` at pad positions (not `pad_token_id`) |
| EOS | Present in label sequence |
| No BOS | `decoder_start_token_id` is in `decoder_input_ids`, not `labels` |

**Check**:
```python
assert decoder_input_ids[:, 0].eq(model.config.decoder_start_token_id).all()
assert (labels == tokenizer.pad_token_id).sum() == 0, "Use -100, not pad_token_id for labels"
```

---

## Regression Checks

### labels

| Property | Expected |
|---|---|
| Shape | `(batch_size,)` or `(batch_size, num_outputs)` |
| Dtype | `float32` |
| Range | Within expected domain (no NaN, no Inf) |
| No integer coercion | Float values, not accidentally rounded |

```python
assert labels.dtype == torch.float32
assert torch.isfinite(labels).all(), "NaN or Inf in regression labels"
```

---

## Padding and Truncation Checks

### Padding consistency

```python
# All sequences in a batch have the same length
seq_lengths = attention_mask.sum(dim=-1)
padded_lengths = (input_ids != tokenizer.pad_token_id).sum(dim=-1)

# Padding token ID is correct
pad_positions = input_ids == tokenizer.pad_token_id
mask_at_pad = attention_mask[pad_positions]
assert (mask_at_pad == 0).all(), "attention_mask is 1 at pad positions"
```

### No empty sequences

```python
assert (seq_lengths > 0).all(), "Some sequences are entirely padding"
```

### Truncation preserves content

```python
# Spot check: decoded first/last token of non-padded region
for i in range(min(3, len(input_ids))):
    actual_len = seq_lengths[i].item()
    first_token = tokenizer.decode([input_ids[i, 0]])
    last_real_token = tokenizer.decode([input_ids[i, actual_len - 1]])
    print(f"Example {i}: first='{first_token}', last_real='{last_real_token}', len={actual_len}")
```

---

## Vision / Image Checks

### pixel_values

| Property | Expected | How to check |
|---|---|---|
| Shape | `(batch, channels, height, width)` | `assert pixel_values.ndim == 4` |
| Dtype | `float32` | `assert pixel_values.dtype == torch.float32` |
| Range (normalized) | `[0.0, 1.0]` or approximately `[-3, 3]` after ImageNet normalization | check min/max |
| Channels | 3 for RGB, 1 for grayscale | `assert pixel_values.shape[1] in (1, 3)` |

```python
print(f"pixel_values: min={pixel_values.min():.3f}, max={pixel_values.max():.3f}")
# For ImageNet normalization, expect roughly [-2.1, 2.6]
# For [0,1] normalization, expect [0.0, 1.0]
```

---

## DataLoader / Collation Checks

### Shape consistency across batches

```python
shapes = []
for i, batch in enumerate(dataloader):
    shapes.append({k: tuple(v.shape) for k, v in batch.items() if hasattr(v, 'shape')})
    if i >= 5: break

# Check no ragged batches
for key in shapes[0]:
    unique_shapes = set(s[key] for s in shapes if key in s)
    if len(unique_shapes) > 1:
        print(f"WARNING: {key} has inconsistent shapes across batches: {unique_shapes}")
```

### No Python objects in batch

```python
for key, val in batch.items():
    if not hasattr(val, 'shape'):
        print(f"WARNING: batch['{key}'] is not a tensor — type: {type(val)}")
```

### Reproducibility with multiple workers

```python
import torch

def worker_init_fn(worker_id):
    torch.manual_seed(42 + worker_id)

loader = DataLoader(dataset, num_workers=4, worker_init_fn=worker_init_fn,
                    generator=torch.Generator().manual_seed(42))
```

---

## Framework-Specific Shape Conventions

| Framework | input_ids shape | labels shape (classification) |
|---|---|---|
| PyTorch (HF) | `(batch, seq_len)` | `(batch,)` |
| TensorFlow (HF) | `(batch, seq_len)` | `(batch,)` |
| JAX/Flax | `(batch, seq_len)` | `(batch,)` |
| PyTorch Lightning | Same as PyTorch | Same as PyTorch |
| DeepSpeed | Same as PyTorch | Same as PyTorch |

TF/JAX note: `int32` is preferred over `int64` for performance on TPU.
