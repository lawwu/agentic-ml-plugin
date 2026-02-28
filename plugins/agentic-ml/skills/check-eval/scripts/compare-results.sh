#!/usr/bin/env bash
# compare-results.sh — diff two lm-evaluation-harness JSON result files and print deltas
# Usage: compare-results.sh baseline.json new.json [--threshold 0.01]
#
# Outputs a delta table comparing metrics between the baseline and new results.
# Metrics that regressed beyond --threshold are flagged with a warning.
# Requires: `uv` plus Python standard library only (json, sys, argparse).

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

uv run python - "$BASELINE" "$NEW_RESULTS" "$THRESHOLD" <<'PYTHON'
import json
import sys

baseline_path, new_path, threshold_str = sys.argv[1], sys.argv[2], sys.argv[3]
threshold = float(threshold_str)


def load_results(path: str) -> dict:
    with open(path) as f:
        data = json.load(f)
    # Support both lm-eval v0.3 and v0.4 output formats
    return data.get("results", data)


def primary_metric(metrics: dict) -> tuple[str, float] | tuple[None, None]:
    """Return (metric_name, value) for the primary metric in a task result."""
    priority = [
        "acc_norm,none", "acc,none", "exact_match,none",
        "word_perplexity,none", "byte_perplexity,none",
        "bleu,none", "rouge1,none", "f1,none",
    ]
    for key in priority:
        if key in metrics and metrics[key] is not None:
            return key, metrics[key]
    # Fall back to first numeric value
    for k, v in metrics.items():
        if isinstance(v, (int, float)) and "stderr" not in k:
            return k, v
    return None, None


baseline = load_results(baseline_path)
new = load_results(new_path)

all_tasks = sorted(set(baseline.keys()) | set(new.keys()))

rows = []
regressions = []
improvements = []

for task in all_tasks:
    if task not in baseline:
        b_val = None
        n_name, n_val = primary_metric(new[task])
        delta = None
        status = "new"
    elif task not in new:
        b_name, b_val = primary_metric(baseline[task])
        n_val = None
        delta = None
        status = "removed"
    else:
        b_name, b_val = primary_metric(baseline[task])
        n_name, n_val = primary_metric(new[task])
        if b_val is not None and n_val is not None:
            delta = n_val - b_val
            if delta < -threshold:
                status = "REGRESSED"
                regressions.append((task, delta))
            elif delta > threshold:
                status = "improved"
                improvements.append((task, delta))
            else:
                status = "~same"
        else:
            delta = None
            status = "?"

    rows.append((task, b_val, n_val, delta, status))

# Print table
header = f"{'Task / Metric':<35} {'Baseline':>10} {'New':>10} {'Delta':>8}  Status"
sep = "-" * len(header)
print(header)
print(sep)

for task, b, n, d, status in rows:
    b_str = f"{b:.4f}" if b is not None else "  —"
    n_str = f"{n:.4f}" if n is not None else "  —"
    d_str = f"{d:+.4f}" if d is not None else "    —"
    flag = " ⚠" if status == "REGRESSED" else (" ✓" if status == "improved" else "")
    print(f"{task:<35} {b_str:>10} {n_str:>10} {d_str:>8}  {status}{flag}")

print(sep)
print(f"Baseline:    {baseline_path}")
print(f"New results: {new_path}")
print(f"Threshold:   ±{threshold}")
print()

if improvements:
    print(f"Improvements ({len(improvements)}):")
    for t, d in sorted(improvements, key=lambda x: -x[1]):
        print(f"  {t}: {d:+.4f}")

if regressions:
    print(f"\nRegressions ({len(regressions)}) — investigate before promoting checkpoint:")
    for t, d in sorted(regressions, key=lambda x: x[1]):
        print(f"  {t}: {d:+.4f}  ⚠")
    sys.exit(1)  # Non-zero exit if regressions detected
else:
    print("No regressions detected.")
PYTHON
