# Compute Estimation Guide

Reference for `plan-experiment`. Use these heuristics to estimate GPU-hours and cost before running experiments.

---

## Default Cloud Cost Assumption

Use **$3 / GPU-hour** unless the user specifies a cluster or spot pricing. Common alternatives:

| Instance type | Approx cost/hr |
|---------------|----------------|
| A100 40 GB (on-demand) | $3.00 |
| A100 80 GB (on-demand) | $4.50 |
| H100 80 GB (on-demand) | $8.00 |
| A10G (spot) | $0.75 |
| T4 (spot) | $0.20 |

---

## Throughput Heuristics by Model Family

### Tabular Models (CPU)

| Model | Dataset size | Est. wall-clock per trial |
|-------|-------------|--------------------------|
| Logistic regression | Any | < 1 min |
| Random forest (1000 trees) | 100K rows | 1–3 min |
| XGBoost / LightGBM | 1M rows, 100 features | 2–10 min |
| XGBoost / LightGBM | 10M rows, 100 features | 10–60 min |

> Tabular models run on CPU. GPU-hours = 0; cost is negligible unless using large cloud VMs.

### MLP / Tabular DL (GPU)

| Dataset size | Est. epoch time (A10G) | Est. total (10 epochs) |
|-------------|----------------------|------------------------|
| 10K rows | ~5 sec | ~1 min |
| 100K rows | ~20 sec | ~3 min |
| 1M rows | ~3 min | ~30 min |

> Rule of thumb: ~1M samples/min throughput on an A10G for a shallow MLP.

### Transformer Fine-tuning (GPU)

| Model size | Seq length | Batch size | Tokens/sec (A100 40G) | 1K-step time |
|-----------|------------|------------|----------------------|--------------|
| 125M (GPT-2) | 512 | 32 | ~80K | ~10 min |
| 7B (LLaMA) | 2048 | 4 | ~5K | ~60 min |
| 13B (LLaMA) | 2048 | 2 | ~2K | ~2.5 hr |
| 70B (LLaMA, 4-GPU) | 2048 | 8 | ~3K | ~4 hr |

> For LoRA fine-tuning: throughput is ~2–3× higher than full fine-tuning at same batch size.

---

## Estimation Formula

```
GPU-hours = (dataset_size × num_epochs) / (throughput × 3600)
```

Or for trial-based search:

```
total_GPU-hours = num_trials × avg_trial_GPU-hours
```

### Example

> XGBoost, 500K rows, 30 trials, avg 10 min/trial:
> total = 30 × (10/60) hr = 5 CPU-hours ≈ $0 GPU cost

> LLaMA 7B fine-tune, 10K examples, 3 epochs, 1 trial:
> steps ≈ 10K × 3 / batch_size(4) = 7500 steps
> time ≈ 7500 / (5K tok/sec / 2048 tok/seq) ≈ 7500 / 2.4 ≈ 3125 sec ≈ 0.9 GPU-hr ≈ $2.70

---

## Budget Allocation Rules

| Total budget | Strategy |
|-------------|----------|
| < 1 GPU-hr | CPU-only models (GBM, linear) + 1 small NN |
| 1–10 GPU-hr | GBM baseline + 1–2 small transformer or MLP candidates |
| 10–50 GPU-hr | Full HP search for 3 candidates with successive halving |
| > 50 GPU-hr | Full search + larger models; apply Hyperband |

---

## Dataset Size Flags

| Rows | Recommendation |
|------|---------------|
| < 1K | Baseline + simple models only; no deep learning |
| 1K – 10K | GBM + small MLP; transformer only with pretrained backbone |
| 10K – 1M | Full candidate set appropriate |
| > 1M | Ensure data pipeline can stream; limit eval frequency |

---

## Multi-GPU Scaling Efficiency

| # GPUs | Typical efficiency |
|--------|-------------------|
| 1 | 100% |
| 2 | 85–90% |
| 4 | 70–80% |
| 8 | 60–70% |

Adjust GPU-hour estimates accordingly: `N-GPU job × efficiency` before multiplying by cost/hr.
