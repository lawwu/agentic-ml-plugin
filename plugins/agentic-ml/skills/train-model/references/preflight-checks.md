# Pre-flight Checks

Cheap checks to run before a full training run. Each catches a class of bug that otherwise burns hours of compute, or produces a model that looks fine and isn't. Record each result as `pass` / `fail` / `skipped` (with the reason) in `train-model.json` under `preflight`.

Run the checks on a **copy** of the model, or re-initialize afterwards, so the real run starts fresh. Use `train` rows only.

## Neural networks

### 1. Loss at initialization

A freshly initialized model should be about as unsure as chance. A very different starting loss points to a bad output layer, wrong loss function, wrong label encoding, or unnormalized inputs.

| Loss | Expected at init |
|---|---|
| Cross-entropy, C balanced classes | ≈ ln C (2.30 for 10 classes) |
| Binary cross-entropy, positive rate p | ≈ −p ln p − (1−p) ln(1−p) (0.69 at p=0.5) |
| MSE on standardized targets | ≈ 1 |
| Causal LM, vocabulary V | ≈ ln V for a randomly initialized model; a pretrained model starts much lower |

```python
import math, torch
xb, yb = next(iter(train_loader))
with torch.no_grad():
    loss0 = loss_fn(model(xb), yb).item()
expected = math.log(num_classes)
print(f"init loss {loss0:.3f}, expected ≈ {expected:.3f}")
# fail if off by more than ~50%
```

### 2. Overfit one batch

A model that cannot drive the loss on 8–32 examples close to zero cannot learn the full problem: there is a bug in the labels, the loss, the masking, or the optimizer setup.

```python
import copy, torch
probe = copy.deepcopy(model).train()
opt = torch.optim.Adam(probe.parameters(), lr=1e-3)
for step in range(300):
    opt.zero_grad()
    loss = loss_fn(probe(xb), yb)
    loss.backward()
    opt.step()
print(f"after 300 steps: {loss.item():.4f} (start {loss0:.4f})")
# pass if the loss falls below ~5% of the starting loss
```

Framework shortcuts:

- **Lightning:** `Trainer(overfit_batches=1, max_epochs=200)`. Use `Trainer(fast_dev_run=True)` for a one-batch smoke run of train, val, and test loops.
- **HF Trainer:** train on `train_dataset.select(range(16))` with `num_train_epochs=50`, `eval_strategy="no"`, and check that the logged training loss approaches zero.
- **LLM fine-tuning:** also decode one training example after the collator and confirm that the loss is computed only on response tokens (prompt tokens masked with `-100`) and the chat template matches the base model's.

### 3. Save, resume, continue

Long runs fail. Check that a checkpoint saves and resumes before you depend on it.

1. Run the real training command with a small step cap and frequent saves (e.g. `--max_steps 20 --save_steps 10`).
2. Re-run it with the resume flag (`resume_from_checkpoint=True` for HF Trainer, `ckpt_path="last"` for Lightning, or the script's own flag) and `--max_steps 30`.
3. Pass if the step counter continues from 20 (not 0), the learning-rate schedule continues, and the loss right after resuming is close to the loss before saving.

Delete the probe checkpoints afterwards, or write them to `<out-dir>/preflight/`.

## Gradient-boosted trees and scikit-learn

```python
import numpy as np
from sklearn.metrics import roc_auc_score

sample = train.sample(min(len(train), 5000), random_state=0)
pipe.fit(sample[features], sample[label])                 # 1) completes
p = pipe.predict_proba(val[features])[:, 1]
assert np.std(p) > 1e-6, "constant predictions"           # 2) not constant
n_out = len(pipe[:-1].get_feature_names_out())            # 3) features as expected
auc = roc_auc_score(val[label], p)
if auc >= 0.99:                                           # 4) too good to be true
    print("near-perfect validation AUC after a quick fit — run a leakage check first")
```

With the bundled scaffold, a quick `train_tabular.py train --model logreg` run covers checks 1–3. Check 4 is the most valuable: a near-perfect score on a small sample almost always means leakage (a target echo, a post-outcome feature, or entity overlap), not a great model.

Also confirm that the feature columns match the data contract from `check-dataset-quality` (`data-contract.json`), with no id, timestamp, or label columns among the features unless intended.
