# HuggingFace Evaluation Patterns

Reference for the `eval-run` skill. Loading and evaluating different HF model types with precision and device mapping.

---

## Checkpoint Loading

### Basic checkpoint loading

```python
from transformers import AutoModelForSequenceClassification, AutoTokenizer
import torch

checkpoint = "./runs/my-model/checkpoint-5000"

tokenizer = AutoTokenizer.from_pretrained(checkpoint)
model = AutoModelForSequenceClassification.from_pretrained(
    checkpoint,
    torch_dtype=torch.bfloat16,   # or float16, float32
    device_map="auto",             # automatic device placement
)
model.eval()
```

### Device and dtype selection

| Scenario | Recommended dtype | device_map |
|---|---|---|
| Single GPU, < 24 GB | `bfloat16` (A100/H100) or `float16` (V100/T4) | `"cuda:0"` |
| Multi-GPU, large model | `bfloat16` | `"auto"` (tensor parallelism via accelerate) |
| CPU-only | `float32` | `"cpu"` |
| 4-bit quantization | Use `BitsAndBytesConfig` | `"auto"` |

```python
# Memory estimate before loading
def estimate_model_memory_gb(num_params: int, dtype: torch.dtype) -> float:
    bytes_per_param = {torch.float32: 4, torch.float16: 2, torch.bfloat16: 2}
    return num_params * bytes_per_param.get(dtype, 2) / 1e9

# Load model config to get param count without loading weights
from transformers import AutoConfig
config = AutoConfig.from_pretrained(checkpoint)
# config.num_parameters() not always available; use model.num_parameters() after load
```

### 4-bit / 8-bit quantized loading

```python
from transformers import BitsAndBytesConfig

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_use_double_quant=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
)

model = AutoModelForCausalLM.from_pretrained(
    checkpoint,
    quantization_config=bnb_config,
    device_map="auto",
)
```

### PEFT/LoRA checkpoint loading

```python
from peft import PeftModel

base_model = AutoModelForCausalLM.from_pretrained(
    "meta-llama/Llama-2-7b-hf",
    torch_dtype=torch.bfloat16,
    device_map="auto",
)
model = PeftModel.from_pretrained(base_model, checkpoint)
model = model.merge_and_unload()  # merge LoRA weights for inference
model.eval()
```

---

## HF Trainer.evaluate()

### Running Trainer evaluation

```python
from transformers import Trainer, TrainingArguments

training_args = TrainingArguments(
    output_dir="./eval_output",
    per_device_eval_batch_size=32,      # set separately from train batch size
    dataloader_num_workers=4,
    bf16=True,
    report_to="none",                   # disable W&B/MLflow for eval-only runs
)

trainer = Trainer(
    model=model,
    args=training_args,
    eval_dataset=eval_dataset,
    tokenizer=tokenizer,
    compute_metrics=compute_metrics,
)

results = trainer.evaluate()
print(results)  # {'eval_loss': 0.234, 'eval_accuracy': 0.912, ...}
```

### compute_metrics for common tasks

```python
import evaluate
import numpy as np

# Classification
accuracy = evaluate.load("accuracy")
f1 = evaluate.load("f1")

def compute_metrics_classification(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    return {
        "accuracy": accuracy.compute(predictions=preds, references=labels)["accuracy"],
        "f1_macro": f1.compute(predictions=preds, references=labels, average="macro")["f1"],
    }

# NER / Token classification
seqeval = evaluate.load("seqeval")

def compute_metrics_ner(eval_pred):
    logits, labels = eval_pred
    preds = np.argmax(logits, axis=-1)
    # Convert to label strings (filter -100)
    true_labels = [[label_list[l] for l in row if l != -100] for row in labels]
    true_preds = [[label_list[p] for p, l in zip(pr, la) if l != -100]
                  for pr, la in zip(preds, labels)]
    return seqeval.compute(predictions=true_preds, references=true_labels)
```

---

## Language Model Perplexity

### Compute perplexity on a held-out set

```python
import torch
import math
from transformers import AutoModelForCausalLM, AutoTokenizer
from torch.utils.data import DataLoader

def compute_perplexity(model, tokenizer, texts, batch_size=4, max_length=512):
    model.eval()
    total_loss = 0.0
    total_tokens = 0

    encodings = tokenizer(
        texts,
        truncation=True,
        max_length=max_length,
        padding=True,
        return_tensors="pt",
    )

    loader = DataLoader(
        list(zip(encodings["input_ids"], encodings["attention_mask"])),
        batch_size=batch_size,
    )

    with torch.no_grad():
        for input_ids, attention_mask in loader:
            input_ids = input_ids.to(model.device)
            attention_mask = attention_mask.to(model.device)
            labels = input_ids.clone()
            labels[attention_mask == 0] = -100  # mask padding from loss

            outputs = model(input_ids=input_ids, attention_mask=attention_mask, labels=labels)
            # outputs.loss is mean over non-masked tokens
            num_tokens = (labels != -100).sum().item()
            total_loss += outputs.loss.item() * num_tokens
            total_tokens += num_tokens

    avg_loss = total_loss / total_tokens
    return math.exp(avg_loss)

ppl = compute_perplexity(model, tokenizer, eval_texts)
print(f"Perplexity: {ppl:.2f}")
```

---

## Generation-Based Evaluation

### BLEU / ROUGE for seq2seq

```python
from transformers import pipeline
import evaluate

bleu = evaluate.load("sacrebleu")
rouge = evaluate.load("rouge")

translator = pipeline(
    "translation",
    model=model,
    tokenizer=tokenizer,
    device=0,
    batch_size=16,
)

predictions = [p["translation_text"] for p in translator(source_texts)]
bleu_score = bleu.compute(predictions=predictions, references=[[r] for r in reference_texts])
rouge_score = rouge.compute(predictions=predictions, references=reference_texts)
print(f"BLEU: {bleu_score['score']:.2f}")
print(f"ROUGE-L: {rouge_score['rougeL']:.4f}")
```

### Greedy vs beam search generation

```python
# Greedy (fast, deterministic)
outputs = model.generate(input_ids, max_new_tokens=128, do_sample=False)

# Beam search (better quality)
outputs = model.generate(input_ids, max_new_tokens=128, num_beams=4, early_stopping=True)

# Sampling (non-deterministic — set seed for reproducibility)
torch.manual_seed(42)
outputs = model.generate(input_ids, max_new_tokens=128, do_sample=True, temperature=0.7, top_p=0.9)
```

---

## Common Pitfalls

| Issue | Symptom | Fix |
|---|---|---|
| Eval batch size too large | OOM during eval | Set `per_device_eval_batch_size` explicitly |
| Model in train mode | Dropout active, results non-deterministic | Call `model.eval()` before evaluation |
| Wrong dtype | Slow eval on bf16-capable hardware | Match `torch_dtype` to training dtype |
| Tokenizer padding side | Wrong results for causal LM batched generation | `tokenizer.padding_side = "left"` for generation |
| `compute_metrics` missing | Only `eval_loss` reported | Implement and pass `compute_metrics` to Trainer |
| Label shift for causal LM | `eval_loss` artificially low | Ensure labels are shifted input_ids with `-100` padding |
| Flash Attention 2 | Not enabled by default | `model = AutoModel.from_pretrained(..., attn_implementation="flash_attention_2")` |
