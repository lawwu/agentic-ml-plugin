#!/usr/bin/env bash
# compare-results.sh — diff two evaluation result JSON files and print deltas
# Usage: compare-results.sh baseline.json new.json [--threshold 0.01]
#
# Accepts lm-evaluation-harness output ({"results": {task: {metric: value}}}),
# a {task: {metric: value}} map, or a flat HF Trainer eval_results.json /
# all_results.json ({"eval_loss": 0.4, "eval_accuracy": 0.8}).
#
# Every metric present in BOTH files is compared under the same name. Metrics
# where lower is better (loss, perplexity, rmse, mae, wer, ...) count a decrease
# as an improvement. Changes worse than --threshold (absolute) are flagged and
# the script exits 1.
# Requires: `uv` plus Python standard library only.

set -euo pipefail

BASELINE="${1:?Usage: compare-results.sh baseline.json new.json [--threshold 0.01]}"
NEW_RESULTS="${2:?Missing new results file}"
THRESHOLD="0.01"

shift 2
while [[ $# -gt 0 ]]; do
    case "$1" in
        --threshold)
            if [[ $# -lt 2 ]]; then
                echo "[ERROR] --threshold requires a numeric value" >&2
                exit 1
            fi
            THRESHOLD="$2"
            shift 2
            ;;
        *)
            # Backward compatible: allow plain positional threshold as third arg.
            THRESHOLD="$1"
            shift
            ;;
    esac
done

if ! [[ "$THRESHOLD" =~ ^([0-9]+([.][0-9]+)?|[.][0-9]+)$ ]]; then
    echo "[ERROR] Invalid threshold: $THRESHOLD" >&2
    exit 1
fi

if [[ ! -f "$BASELINE" ]]; then
    echo "[ERROR] Baseline file not found: $BASELINE" >&2
    exit 1
fi

if [[ ! -f "$NEW_RESULTS" ]]; then
    echo "[ERROR] New results file not found: $NEW_RESULTS" >&2
    exit 1
fi

# --no-project: never create or sync a .venv in the user's project directory.
uv run --no-project python - "$BASELINE" "$NEW_RESULTS" "$THRESHOLD" <<'PYTHON'
import json
import re
import sys

baseline_path, new_path, threshold_str = sys.argv[1], sys.argv[2], sys.argv[3]
threshold = float(threshold_str)

LOWER_IS_BETTER = re.compile(
    r"(^|[_\-\s])(loss|log_loss|logloss|nll|perplexity|ppl|rmse|mse|mae|mape|smape|"
    r"wer|cer|ter|bpb|bits_per_byte|brier|brier_score|error|err)($|[_\-\s])"
)
# Bookkeeping fields in HF Trainer outputs; not quality metrics.
IGNORED = re.compile(r"(runtime|_per_second|^epoch$|^step$|^total_flos$|^num_|_samples$)")


def metric_base(name: str) -> str:
    """'word_perplexity,none' -> 'word_perplexity'; 'eval_loss' -> 'eval_loss'."""
    return name.split(",", 1)[0].strip().lower()


def lower_is_better(name: str) -> bool:
    return bool(LOWER_IS_BETTER.search(metric_base(name)))


def is_metric(name: str, value) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    base = metric_base(name)
    return "stderr" not in base and not IGNORED.search(base)


def load_results(path: str) -> dict:
    """Return {task: {metric: value}}."""
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, dict):
        sys.exit(f"[ERROR] {path}: expected a JSON object")
    results = data.get("results", data)
    if not isinstance(results, dict):
        sys.exit(f"[ERROR] {path}: 'results' is not an object")
    tasks = {}
    flat = {}
    for key, value in results.items():
        if isinstance(value, dict):
            metrics = {k: v for k, v in value.items() if is_metric(k, v)}
            if metrics:
                tasks[key] = metrics
        elif is_metric(key, value):
            flat[key] = value  # HF Trainer style flat file
    if flat:
        tasks.setdefault("(overall)", {}).update(flat)
    return tasks


baseline = load_results(baseline_path)
new = load_results(new_path)

rows = []
regressions = []
improvements = []

for task in sorted(set(baseline) | set(new)):
    b_metrics = baseline.get(task, {})
    n_metrics = new.get(task, {})
    for metric in sorted(set(b_metrics) | set(n_metrics)):
        label = f"{task} / {metric}"
        b_val = b_metrics.get(metric)
        n_val = n_metrics.get(metric)
        if b_val is None:
            rows.append((label, None, n_val, None, "new"))
            continue
        if n_val is None:
            rows.append((label, b_val, None, None, "removed"))
            continue
        delta = n_val - b_val
        lib = lower_is_better(metric)
        gain = -delta if lib else delta  # positive = better
        if gain < -threshold:
            status = "REGRESSED"
            regressions.append((label, delta, lib))
        elif gain > threshold:
            status = "improved"
            improvements.append((label, delta, lib))
        else:
            status = "~same"
        if lib:
            status += " (lower=better)"
        rows.append((label, b_val, n_val, delta, status))

if not rows:
    sys.exit("[ERROR] No numeric metrics found in either file")

width = max(35, max(len(r[0]) for r in rows) + 1)
header = f"{'Task / Metric':<{width}} {'Baseline':>10} {'New':>10} {'Delta':>9}  Status"
sep = "-" * len(header)
print(header)
print(sep)

for label, b, n, d, status in rows:
    b_str = f"{b:.4f}" if b is not None else "  —"
    n_str = f"{n:.4f}" if n is not None else "  —"
    d_str = f"{d:+.4f}" if d is not None else "    —"
    flag = " ⚠" if status.startswith("REGRESSED") else (" ✓" if status.startswith("improved") else "")
    print(f"{label:<{width}} {b_str:>10} {n_str:>10} {d_str:>9}  {status}{flag}")

print(sep)
print(f"Baseline:    {baseline_path}")
print(f"New results: {new_path}")
print(f"Threshold:   ±{threshold} (absolute)")
compared = sum(1 for r in rows if r[3] is not None)
print(f"Compared:    {compared} metric(s) present in both files")
print()

if improvements:
    print(f"Improvements ({len(improvements)}):")
    for t, d, lib in sorted(improvements, key=lambda x: -abs(x[1])):
        print(f"  {t}: {d:+.4f}{' (lower=better)' if lib else ''}")

if regressions:
    print(f"\nRegressions ({len(regressions)}) — investigate before promoting checkpoint:")
    for t, d, lib in sorted(regressions, key=lambda x: -abs(x[1])):
        print(f"  {t}: {d:+.4f}{' (lower=better)' if lib else ''}  ⚠")
    sys.exit(1)  # Non-zero exit if regressions detected
elif compared == 0:
    print("No metrics in common between the two files — nothing compared.")
    sys.exit(2)
else:
    print("No regressions detected.")
PYTHON
