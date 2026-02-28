# Framework Patterns

Reference for the `data-pipeline-validate` skill. Code templates for writing inline validation scripts per framework and pipeline type.

---

## HuggingFace `datasets.map` Pipeline

### Tokenizer validation template

```python
from transformers import AutoTokenizer
from datasets import load_dataset
import torch

CHECKPOINT = "bert-base-uncased"
DATASET = "glue"
TASK = "sst2"
BATCH_SIZE = 16
MAX_LENGTH = 128

tokenizer = AutoTokenizer.from_pretrained(CHECKPOINT)
ds = load_dataset(DATASET, TASK, split="train[:64]")  # 64 examples for validation

def tokenize_fn(examples):
    return tokenizer(
        examples["sentence"],
        max_length=MAX_LENGTH,
        truncation=True,
        padding="max_length",
    )

tokenized = ds.map(tokenize_fn, batched=True, remove_columns=["sentence", "idx"])
tokenized.set_format("torch", columns=["input_ids", "attention_mask", "label"])

loader = torch.utils.data.DataLoader(tokenized, batch_size=BATCH_SIZE)

print("=== Pipeline Validation ===")
passed = 0
failed = []

for i, batch in enumerate(loader):
    if i >= 4:  # check first 4 batches
        break

    input_ids = batch["input_ids"]
    attention_mask = batch["attention_mask"]
    labels = batch["label"]

    checks = [
        ("input_ids.ndim == 2", input_ids.ndim == 2),
        ("input_ids.dtype == int64", input_ids.dtype == torch.long),
        ("input_ids range valid", input_ids.max() < tokenizer.vocab_size and input_ids.min() >= 0),
        ("attention_mask binary", set(attention_mask.unique().tolist()).issubset({0, 1})),
        ("attention_mask shape matches", attention_mask.shape == input_ids.shape),
        ("no all-zero sequences", (attention_mask.sum(dim=-1) > 0).all().item()),
        ("labels dtype int64", labels.dtype == torch.long),
        ("labels in [0, num_classes)", labels.min() >= 0),
    ]

    for name, result in checks:
        if result:
            passed += 1
        else:
            failed.append(f"Batch {i}: {name}")

print(f"Checks passed: {passed}/{passed + len(failed)}")
for f in failed:
    print(f"  FAIL: {f}")
```

---

## PyTorch DataLoader with Custom Dataset

### DataLoader validation template

```python
import torch
from torch.utils.data import DataLoader

# Assume: train_dataset is your dataset, collate_fn is your collator
BATCH_SIZE = 16
NUM_WORKERS = 0  # Use 0 for validation to get clean tracebacks

loader = DataLoader(
    train_dataset,
    batch_size=BATCH_SIZE,
    num_workers=NUM_WORKERS,
    collate_fn=collate_fn,
    shuffle=False,
)

print("=== DataLoader Validation ===")
errors = []

for i, batch in enumerate(loader):
    if i >= 4:
        break

    # Print shapes on first batch
    if i == 0:
        print("Batch structure:")
        for key, val in batch.items():
            if hasattr(val, 'shape'):
                print(f"  {key}: shape={val.shape}, dtype={val.dtype}")
            else:
                print(f"  {key}: type={type(val)} (WARNING: not a tensor)")

    # Core checks
    if "input_ids" in batch:
        ids = batch["input_ids"]
        if ids.ndim != 2:
            errors.append(f"Batch {i}: input_ids has {ids.ndim} dims (expected 2)")
        if ids.dtype != torch.long:
            errors.append(f"Batch {i}: input_ids dtype={ids.dtype} (expected torch.long)")

    if "labels" in batch:
        lbl = batch["labels"]
        if torch.is_floating_point(lbl) and task == "classification":
            errors.append(f"Batch {i}: labels are float (expected int for classification)")
        if lbl.isnan().any():
            errors.append(f"Batch {i}: NaN in labels")

print(f"\n{'All checks passed.' if not errors else chr(10).join(errors)}")
```

---

## Causal Language Modeling (GPT-style)

### Label shift validation

```python
from transformers import AutoTokenizer, DataCollatorForLanguageModeling
from datasets import load_dataset
import torch

tokenizer = AutoTokenizer.from_pretrained("gpt2")
tokenizer.pad_token = tokenizer.eos_token

ds = load_dataset("wikitext", "wikitext-2-raw-v1", split="train[:64]")

def tokenize(examples):
    return tokenizer(examples["text"], truncation=True, max_length=512)

tokenized = ds.map(tokenize, batched=True, remove_columns=["text"])
collator = DataCollatorForLanguageModeling(tokenizer=tokenizer, mlm=False)

loader = torch.utils.data.DataLoader(
    tokenized, batch_size=8, collate_fn=collator
)

batch = next(iter(loader))
input_ids = batch["input_ids"]
labels = batch["labels"]

print("=== Causal LM Label Shift Validation ===")

# Verify label shift: labels[i] should equal input_ids[i+1]
# (ignoring -100 positions)
valid_mask = labels[:, :-1] != -100
expected_labels = input_ids[:, 1:]
actual_labels = labels[:, :-1]

mismatch = (valid_mask & (expected_labels != actual_labels)).sum().item()
if mismatch == 0:
    print("PASS: labels are correctly shifted input_ids")
else:
    print(f"FAIL: {mismatch} positions have wrong label shift")

# Verify last token is masked
last_masked = (labels[:, -1] == -100).all().item()
print(f"{'PASS' if last_masked else 'FAIL'}: last label position is -100")

# Verify EOS handling
eos_in_labels = (labels == tokenizer.eos_token_id).any().item()
print(f"{'PASS' if eos_in_labels else 'WARN'}: EOS token appears in labels")
```

---

## Seq2Seq (T5/mBART style)

### Encoder-decoder validation template

```python
from transformers import AutoTokenizer, DataCollatorForSeq2Seq
import torch

tokenizer = AutoTokenizer.from_pretrained("t5-small")
model_config_decoder_start = tokenizer.pad_token_id  # T5 uses pad as BOS

def preprocess(examples):
    inputs = tokenizer(examples["source"], max_length=128, truncation=True, padding=False)
    with tokenizer.as_target_tokenizer():
        targets = tokenizer(examples["target"], max_length=64, truncation=True, padding=False)
    inputs["labels"] = targets["input_ids"]
    return inputs

collator = DataCollatorForSeq2Seq(tokenizer, model=None, padding=True, label_pad_token_id=-100)

# Load sample batch
batch = collator([preprocess({"source": "translate: Hello world", "target": "Bonjour le monde"})])

print("=== Seq2Seq Validation ===")
input_ids = batch["input_ids"]
labels = batch["labels"]

# Decoder input IDs should start with decoder_start_token_id
dec_input = batch.get("decoder_input_ids")
if dec_input is not None:
    first_tokens = dec_input[:, 0]
    ok = (first_tokens == model_config_decoder_start).all().item()
    print(f"{'PASS' if ok else 'FAIL'}: decoder_input_ids starts with decoder_start_token_id")

# Labels should not contain pad_token_id (should be -100 instead)
pad_in_labels = (labels == tokenizer.pad_token_id).any().item()
print(f"{'FAIL' if pad_in_labels else 'PASS'}: labels use -100 (not pad_token_id) for padding")

# Labels should contain EOS
eos_in_labels = (labels == tokenizer.eos_token_id).any().item()
print(f"{'PASS' if eos_in_labels else 'WARN'}: EOS token present in labels")
```

---

## Token Classification (NER)

### Subword label alignment validation

```python
from transformers import AutoTokenizer
import torch

tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")

text = "John Smith works at OpenAI in San Francisco"
labels_per_word = [1, 1, 0, 0, 3, 0, 3, 3]  # BIO-encoded: 1=B-PER, 3=B-LOC, 0=O

encoding = tokenizer(text.split(), is_split_into_words=True, return_offsets_mapping=True,
                     return_tensors="pt", padding=True, truncation=True, max_length=32)

word_ids = encoding.word_ids(batch_index=0)

aligned_labels = []
prev_word_id = None
for word_id in word_ids:
    if word_id is None:
        aligned_labels.append(-100)  # [CLS], [SEP], [PAD]
    elif word_id != prev_word_id:
        aligned_labels.append(labels_per_word[word_id])  # First subword: real label
    else:
        aligned_labels.append(-100)  # Non-first subword: ignore
    prev_word_id = word_id

label_tensor = torch.tensor([aligned_labels])

print("=== Token Classification Alignment Validation ===")
# Shape check
ok_shape = label_tensor.shape == encoding["input_ids"].shape
print(f"{'PASS' if ok_shape else 'FAIL'}: labels shape matches input_ids shape")

# Range check (excluding -100)
valid_labels = label_tensor[label_tensor != -100]
num_label_classes = 4  # update to your num_labels
ok_range = (valid_labels >= 0).all() and (valid_labels < num_label_classes).all()
print(f"{'PASS' if ok_range else 'FAIL'}: label values in [0, num_labels)")

# Special token positions are -100
special_positions = [i for i, wid in enumerate(word_ids) if wid is None]
special_labels = [label_tensor[0][p].item() for p in special_positions]
ok_special = all(l == -100 for l in special_labels)
print(f"{'PASS' if ok_special else 'FAIL'}: special token positions have label -100")
```

---

## Tokenizer Configuration Checklist

Quick reference for common tokenizer configuration mistakes:

| Issue | Symptom | Fix |
|---|---|---|
| No pad token | `ValueError: pad_token is not set` | `tokenizer.pad_token = tokenizer.eos_token` (GPT-style) |
| Padding side | Right-padded by default; causal LMs need left-padding for generation | `tokenizer.padding_side = "left"` |
| Truncation disabled | Sequences > model max_length cause index OOB in positional embeddings | `truncation=True` in tokenizer call |
| `add_special_tokens=False` | Missing CLS/SEP → wrong attention pattern | Only suppress when doing packing/concatenation |
| Wrong `return_tensors` | Lists instead of tensors in batch | `return_tensors="pt"` (PyTorch) or `"tf"` (TF) |
| Max length mismatch | Truncation at wrong length | `max_length=model.config.max_position_embeddings` |
