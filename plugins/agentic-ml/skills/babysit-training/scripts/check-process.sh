#!/usr/bin/env bash
# check-process.sh — check if a training process is alive (local or remote)
# Usage: check-process.sh [user@host] PID|PROC_NAME
#
# For remote checks, pass user@host as first arg.
# For local checks, omit the first arg or pass "local".
#
# Outputs: JSON with fields: alive (bool), info (process lines), gpu_stats (optional)

set -euo pipefail

if [[ $# -eq 0 ]]; then
    echo "Usage: $0 [user@host] PID|PROC_NAME" >&2
    exit 1
fi

if [[ $# -eq 1 ]]; then
    TARGET="local"
    IDENTIFIER="$1"
else
    TARGET="$1"
    IDENTIFIER="$2"
fi

SSH_OPTS=(-o ConnectTimeout=10 -o BatchMode=yes)

escape_for_shell() {
    printf "%q" "$1"
}

run_ps() {
    local pid="$1"
    if [[ "$TARGET" == "local" ]]; then
        ps -p "$pid" -o pid=,comm=,etime= 2>/dev/null || true
    else
        ssh "${SSH_OPTS[@]}" "$TARGET" "ps -p $pid -o pid=,comm=,etime= 2>/dev/null || true" 2>/dev/null || true
    fi
}

run_pgrep() {
    local name="$1"
    if [[ "$TARGET" == "local" ]]; then
        pgrep -a -- "$name" 2>/dev/null | head -5 || true
    else
        local escaped_name
        escaped_name="$(escape_for_shell "$name")"
        ssh "${SSH_OPTS[@]}" "$TARGET" "pgrep -a -- $escaped_name 2>/dev/null | head -5 || true" 2>/dev/null || true
    fi
}

run_gpu_probe() {
    if [[ "$TARGET" == "local" ]]; then
        nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -4 || true
    else
        ssh "${SSH_OPTS[@]}" "$TARGET" "nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -4 || true" 2>/dev/null || true
    fi
}

if [[ "$IDENTIFIER" =~ ^[0-9]+$ ]]; then
    PROC_INFO="$(run_ps "$IDENTIFIER")"
else
    PROC_INFO="$(run_pgrep "$IDENTIFIER")"
fi

GPU_INFO="$(run_gpu_probe)"

PROC_INFO="$PROC_INFO" GPU_INFO="$GPU_INFO" uv run python - <<'PYTHON'
import json
import os

proc_info = os.environ.get("PROC_INFO", "").strip()
gpu_info = os.environ.get("GPU_INFO", "").strip()

payload = {"alive": bool(proc_info)}
if proc_info:
    payload["info"] = [line.strip() for line in proc_info.splitlines() if line.strip()]

if gpu_info:
    gpu_rows = []
    for line in gpu_info.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) != 3:
            continue
        util, mem_used, mem_total = parts
        if not (util.isdigit() and mem_used.isdigit() and mem_total.isdigit()):
            continue
        gpu_rows.append(
            {
                "utilization_gpu_pct": int(util),
                "memory_used_mb": int(mem_used),
                "memory_total_mb": int(mem_total),
            }
        )
    if gpu_rows:
        payload["gpu_stats"] = gpu_rows

print(json.dumps(payload))
PYTHON
