# lm-evaluation-harness Reference

Reference for the `eval-run` skill. lm-evaluation-harness (lm_eval) CLI reference, common tasks, and output parsing.

---

## Installation

```bash
uv pip install lm-eval
# or from source for latest tasks:
uv pip install git+https://github.com/EleutherAI/lm-evaluation-harness.git
```

---

## Core CLI Usage

### Basic evaluation

```bash
uv run lm_eval \
  --model hf \
  --model_args pretrained=./checkpoint,dtype=bfloat16 \
  --tasks hellaswag \
  --batch_size auto \
  --output_path ./results/hellaswag.json
```

### Multiple tasks

```bash
uv run lm_eval \
  --model hf \
  --model_args pretrained=./checkpoint,dtype=bfloat16 \
  --tasks hellaswag,arc_easy,arc_challenge,mmlu,truthfulqa_mc \
  --batch_size auto \
  --output_path ./results/checkpoint-5000.json \
  --log_samples
```

### Common model_args

| Argument | Description | Example |
|---|---|---|
| `pretrained` | Checkpoint path or HF Hub model ID | `pretrained=./checkpoint` |
| `dtype` | Compute dtype | `dtype=bfloat16` |
| `device` | Device | `device=cuda:0` |
| `trust_remote_code` | For custom models | `trust_remote_code=True` |
| `load_in_4bit` | 4-bit quantization | `load_in_4bit=True` |
| `peft` | LoRA adapter path | `peft=./adapter` |
| `parallelize` | Multi-GPU tensor parallel | `parallelize=True` |

Full model_args string: `--model_args pretrained=./ckpt,dtype=bfloat16,device=cuda:0`

---

## Common Task Names

### Commonsense Reasoning

| Task | Metric | Notes |
|---|---|---|
| `hellaswag` | `acc_norm` | Normalized accuracy is primary metric |
| `winogrande` | `acc` | |
| `piqa` | `acc_norm` | |
| `arc_easy` | `acc_norm` | ARC Easy questions |
| `arc_challenge` | `acc_norm` | ARC Challenge questions |
| `openbookqa` | `acc_norm` | |

### Knowledge and QA

| Task | Metric | Notes |
|---|---|---|
| `mmlu` | `acc` | 57 academic subjects; use `mmlu_*` for individual subjects |
| `triviaqa` | `exact_match` | |
| `naturalqs` | `exact_match` | |
| `sciq` | `acc_norm` | |

### Language Modeling (Perplexity)

| Task | Metric | Notes |
|---|---|---|
| `wikitext` | `word_perplexity`, `byte_perplexity` | Standard LM benchmark |
| `lambada_openai` | `acc`, `perplexity` | Last-word prediction |
| `ptb` | `word_perplexity` | Penn Treebank |

### Truthfulness / Safety

| Task | Metric | Notes |
|---|---|---|
| `truthfulqa_mc1` | `acc` | Multiple choice, 1-correct |
| `truthfulqa_mc2` | `acc` | Multiple choice, multiple correct |

### Mathematical Reasoning

| Task | Metric | Notes |
|---|---|---|
| `gsm8k` | `exact_match` | Requires chain-of-thought; use `--num_fewshot 8` |
| `math` | `exact_match` | Requires code interpreter; complex setup |

### Code

| Task | Metric | Notes |
|---|---|---|
| `humaneval` | `pass@1` | Requires `--allow_code_execution` |

### Listing available tasks

```bash
uv run lm_eval --list-tasks 2>&1 | grep -E "^(task|  -)" | head -50
# or
uv run python -c "from lm_eval.tasks import TaskManager; tm = TaskManager(); print(sorted(tm.all_tasks)[:30])"
```

---

## Few-Shot Evaluation

```bash
# 0-shot (default for most tasks)
uv run lm_eval --model hf --model_args pretrained=./ckpt --tasks arc_challenge --num_fewshot 0

# Few-shot (paper standard)
uv run lm_eval --model hf --model_args pretrained=./ckpt --tasks gsm8k --num_fewshot 8
uv run lm_eval --model hf --model_args pretrained=./ckpt --tasks mmlu --num_fewshot 5
uv run lm_eval --model hf --model_args pretrained=./ckpt --tasks hellaswag --num_fewshot 10
```

**Standard few-shot settings** (match leaderboard comparisons):

| Task | k |
|---|---|
| HellaSwag | 10 |
| ARC (easy/challenge) | 25 |
| MMLU | 5 |
| GSM8k | 8 |
| WinoGrande | 5 |

---

## Limiting Evaluation (Smoke Tests)

```bash
# Run on first 100 examples only (fast check)
uv run lm_eval \
  --model hf \
  --model_args pretrained=./ckpt,dtype=bfloat16 \
  --tasks hellaswag \
  --limit 100 \
  --batch_size 8
```

---

## Output Parsing

### JSON output structure

```json
{
  "results": {
    "hellaswag": {
      "acc,none": 0.7823,
      "acc_norm,none": 0.7812,
      "acc_norm_stderr,none": 0.0041
    },
    "arc_easy": {
      "acc,none": 0.7912,
      "acc_norm,none": 0.7889,
      "acc_norm_stderr,none": 0.0085
    }
  },
  "config": {
    "model": "hf",
    "model_args": "pretrained=./checkpoint,dtype=bfloat16",
    "num_fewshot": 0
  }
}
```

### Extracting key metrics

```python
import json

with open("results/checkpoint-5000.json") as f:
    results = json.load(f)

for task, metrics in results["results"].items():
    # Primary metric is usually acc_norm,none or acc,none
    primary = metrics.get("acc_norm,none") or metrics.get("acc,none") or metrics.get("exact_match,none")
    stderr = metrics.get("acc_norm_stderr,none") or metrics.get("acc_stderr,none", 0.0)
    if primary is not None:
        print(f"{task}: {primary:.4f} ± {stderr:.4f}")
```

---

## Debugging Common Errors

### `ValueError: No tasks matching ...`

```bash
# Check exact task name
uv run lm_eval --list-tasks | grep -i "hellaswag"
# Task names are case-sensitive and version-specific
```

### OOM during evaluation

```bash
# Reduce batch size
uv run lm_eval ... --batch_size 1

# Or let harness auto-detect max batch size
uv run lm_eval ... --batch_size auto:4  # start at 4, reduce if OOM
```

### Slow evaluation

```bash
# Use larger batch size
uv run lm_eval ... --batch_size auto

# Use 4-bit quantization for large models
uv run lm_eval ... --model_args pretrained=./ckpt,dtype=bfloat16,load_in_4bit=True
```

### Different scores than reported paper

- Check `--num_fewshot` matches the paper
- Check tokenizer chat template (for instruction-tuned models, use `--apply_chat_template`)
- Check if model requires `trust_remote_code`
- Compare `model_args` — dtype differences (float32 vs bfloat16) can affect results slightly

---

## Reproducibility

```bash
# Pin harness version for reproducibility
uv pip install lm-eval==0.4.3

# Log harness version in results
uv run lm_eval --version  # prints version
# Version is also recorded in output JSON under config.version
```
