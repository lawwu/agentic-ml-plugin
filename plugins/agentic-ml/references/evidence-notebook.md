# Evidence Notebook

Every run keeps one evidence notebook: `<out-dir>/evidence.md`. Each skill appends a section that shows the command behind every headline number and every `blocker`/`high` finding, with that command's real output. Anyone can re-run the whole notebook and check that the outputs still match:

```bash
uvx showboat --workdir <out-dir> verify <out-dir>/evidence.md
```

The notebook is built with [showboat](https://github.com/simonw/showboat). It turns "the agent says the test AUPRC is 0.14" into "here is the command, here is its output, and it still reproduces".

## Commands

Always pass `--workdir <out-dir>`, for `exec` and `verify` alike, so blocks run from the same directory no matter where verify is started.

```bash
# once per run; init refuses to overwrite, so "already exists" means another skill created it — keep going
uvx showboat --workdir <out-dir> init <out-dir>/evidence.md "Evidence — <objective> (<run_id>)"

# section heading and the claim, in one note
uvx showboat --workdir <out-dir> note <out-dir>/evidence.md "## Gate 2 — check-dataset-quality
F001 (blocker): days_until_readmission is filled in only for readmitted patients — a target echo."

# the command that shows it, with its output captured
uvx showboat --workdir <out-dir> exec <out-dir>/evidence.md bash "<command>"

# multi-line code goes in on stdin
uvx showboat --workdir <out-dir> exec <out-dir>/evidence.md bash <<'SH'
uv run --quiet --no-project --with pandas python - <<'PY'
import pandas as pd
d = pd.read_csv("/abs/path/data.csv")
print(pd.crosstab(d.days_until_readmission.notna(), d.readmitted_30d))
PY
SH

# remove the last block if it failed for an unrelated reason (typo, wrong path)
uvx showboat --workdir <out-dir> pop <out-dir>/evidence.md
```

`exec` prints the output and returns the command's exit code. It appends the block even when the command fails. If it failed for an unrelated reason, fix the command and `pop` the bad block. If the failure *is* the evidence (an assertion that should fail), keep it: verify will check that it still fails the same way.

## What a block must be

Verify re-runs every `exec` block and compares output exactly, so each block must be:

| Requirement | How |
|---|---|
| **Deterministic** | Fixed seeds (`--seed`, `--n-boot` with the default seed). No timestamps, latencies, PIDs, temp paths, or unordered output in what is printed. |
| **Side-effect free** | Read run files; write only to `/dev/null` or `"$(mktemp -d)"`. Never overwrite the run's artifacts, and never create the split again in `<out-dir>`. |
| **Fast** | Under about a minute. The whole notebook should verify in a few minutes. |
| **Path-stable** | Run files relative to `<out-dir>` (`predictions/model_val.csv`); data and plugin scripts by absolute path. |
| **Small** | Print a few labeled values (`grep`, `head`, a short Python print), not whole files, so a mismatch is easy to read. |
| **Safe** | No secrets, connection strings with passwords, or personal-data values. Print counts, rates, and hashes, never raw test-set rows. |

Steps that cannot meet these rules — training longer than a minute, monitoring a live job, hosted API calls, latency measurements — are recorded as a **note** containing the exact command (in a fenced block) and the measured result. Follow it with an `exec` block that checks what the step produced: the sha256 of the output files, and the key fields of its metrics file.

## What each section contains

Start each skill's section with a note whose first line is the heading:

- `## Gate <n> — <skill>` inside an orchestrated run
- `## <skill>` standalone

The rest of that note says, in one or two sentences, what the section shows. Then for each item below, write a note stating the claim (with its finding ID when there is one), followed by an `exec` block that shows it:

1. Every headline number the skill reports (scores, deltas, counts, hashes).
2. Every `blocker` and `high` finding.
3. The decision's deciding fact (e.g. "delta interval includes zero → CONDITIONAL").

Each skill's **Record evidence** step lists its specifics.

Recomputing the final test metric from saved test predictions is fine: it re-computes the same number, it is not a new evaluation. Never add a block that scores a different model on the test set.

## Linking from artifacts

In the skill's JSON artifact, set:

- `evidence_notebook`: `"<out-dir>/evidence.md"`
- `evidence_blocks`: how many `exec` blocks this skill added
- for a finding backed by a block: `findings[].evidence` gets `{"kind": "notebook", "ref": "evidence.md", "section": "<heading>", "command": "<the exec command>"}`

## Verifying

`orchestrate-e2e` verifies the notebook at promotion (gate 10). Anyone can verify at any time. Write the output to a file and record the exit code:

```bash
uvx showboat --workdir <out-dir> verify <out-dir>/evidence.md > <out-dir>/evidence-verify.txt 2>&1; echo $?
```

- Exit `0`: every block reproduced.
- Exit `1`: at least one block's output changed. `evidence-verify.txt` shows each changed block with the expected and actual output. Treat it as a `high` finding and show the diff to the user. If the change touches a headline metric, the test hash, or a blocker finding, the decision is `NO-GO` until it is explained.

Verification needs the same machine (or the same absolute data and plugin paths). On another machine, `showboat extract <file>` prints the commands so a reviewer can adapt the paths.

## Without showboat

If `uvx showboat` cannot run (offline, or an agent harness without `uv`), write `evidence.md` by hand in the same shape, with each command in a ` ```bash ` block followed by its pasted output in a ` ```output ` block. Put this line under the title:

> Not verifiable: written without showboat.

Set `verified` to `null`.

## Example

From a readmission run. The full notebook has seven blocks and verifies in about 12 seconds, including a full retrain with 5-fold cross-validation. Changing 5 of 600 test predictions makes verify fail on the gate 10 block.

````markdown
## Gate 2 — check-dataset-quality
F001 (blocker): days_until_readmission is filled in only for readmitted patients — a target echo.

```bash
uv run --quiet --no-project --with pandas python - <<'PY'
import pandas as pd
d = pd.read_csv("/data/readmission.csv")
print(pd.crosstab(d.days_until_readmission.notna(), d.readmitted_30d, rownames=["filled_in"], colnames=["readmitted"]))
PY
```

```output
readmitted  False  True
filled_in
False        3547      0
True            0    453
```

## Gate 7 — check-eval (val)
Model vs. the rule baseline, paired bootstrap. The delta interval includes zero → CONDITIONAL.

```bash
uv run --quiet --no-project /plugins/agentic-ml/skills/check-eval/scripts/eval_report.py --pred predictions/model_val.csv --metric auprc --baseline-pred predictions/baseline_prior-admissions_val.csv --n-boot 1000 --split-manifest splits/split-manifest.json --expect-split val --out /dev/null | grep -E '^auprc|baseline|split check' | sed 's/^ *//'
```

```output
auprc = 0.1416 [0.1019, 0.2124]  (95% CI, binary, n=600, 68 positives, 1000 resamples)
baseline 0.1243 [0.0952, 0.1610]; delta 0.0173 [-0.0188, 0.0811] -> better, not significant, P(not better) = 0.1660
split check (val): OK
```
````
