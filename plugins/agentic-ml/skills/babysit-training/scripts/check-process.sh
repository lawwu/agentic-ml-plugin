#!/usr/bin/env bash
# check-process.sh — check if a training process is alive (local or remote)
# Usage: check-process.sh [user@host|local] PID|PATTERN
#
# PATTERN is matched against the full command line (pgrep -f), so
# `train.py`, `torchrun` or "uv run train" all work. Works on Linux and macOS.
#
# Output (stdout, JSON):
#   alive      true / false, or null when the remote host could not be reached
#   processes  [{pid, stat, etime, command}] for each match (zombies excluded from alive)
#   info       the same matches as raw "pid stat etime command" lines
#   gpu_stats  [{utilization_gpu_pct, memory_used_mb, memory_total_mb}] when nvidia-smi exists
#   error      present only when the check itself failed (e.g. SSH unreachable)
# Exit status: 0 = check ran (alive or not), 2 = check failed (alive unknown).

set -euo pipefail

if [[ $# -eq 0 || $# -gt 2 ]]; then
    echo "Usage: $0 [user@host|local] PID|PATTERN" >&2
    exit 1
fi

if [[ $# -eq 1 ]]; then
    TARGET="local"
    IDENTIFIER="$1"
else
    TARGET="$1"
    IDENTIFIER="$2"
fi

if [[ "$IDENTIFIER" =~ ^[0-9]+$ ]]; then
    MODE="pid"
else
    MODE="pattern"
fi

# POSIX-sh probe, run locally or on the remote host via `sh -s`.
# Excludes itself and its ancestors: their command lines contain PATTERN too
# (e.g. the agent's shell running `check-process.sh train.py`).
read -r -d '' PROBE <<'SH' || true
pattern="$1"; mode="$2"
anc=" $$ "
p=$$
while [ -n "$p" ] && [ "$p" != 0 ] && [ "$p" != 1 ]; do
    p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
    [ -n "$p" ] && anc="$anc$p "
done
if [ "$mode" = pid ]; then
    pids="$pattern"
else
    pids=$(pgrep -f -- "$pattern" 2>/dev/null || true)
fi
for pid in $pids; do
    case "$anc" in *" $pid "*) continue ;; esac
    ps -o pid=,stat=,etime=,args= -p "$pid" 2>/dev/null || true
done | head -n 20
echo "__GPU__"
if command -v nvidia-smi >/dev/null 2>&1; then
    nvidia-smi --query-gpu=utilization.gpu,memory.used,memory.total --format=csv,noheader,nounits 2>/dev/null | head -n 8 || true
fi
SH

# Single-quote a string for a POSIX shell.
sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }

ERR_FILE="$(mktemp)"
trap 'rm -f "$ERR_FILE"' EXIT

RC=0
if [[ "$TARGET" == "local" ]]; then
    OUTPUT="$(sh -s -- "$IDENTIFIER" "$MODE" <<<"$PROBE" 2>"$ERR_FILE")" || RC=$?
else
    OUTPUT="$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$TARGET" \
        "sh -s -- $(sq "$IDENTIFIER") $MODE" <<<"$PROBE" 2>"$ERR_FILE")" || RC=$?
fi

CHECK_ERROR=""
if [[ $RC -ne 0 ]] || [[ "$OUTPUT" != *"__GPU__"* ]]; then
    CHECK_ERROR="probe failed on ${TARGET} (exit ${RC}): $(tr '\n' ' ' <"$ERR_FILE" | cut -c1-300)"
fi

PROC_INFO="${OUTPUT%%__GPU__*}"
GPU_INFO=""
[[ "$OUTPUT" == *"__GPU__"* ]] && GPU_INFO="${OUTPUT#*__GPU__}"

# --no-project: never create or sync a .venv in the user's project directory.
PROC_INFO="$PROC_INFO" GPU_INFO="$GPU_INFO" CHECK_ERROR="$CHECK_ERROR" TARGET="$TARGET" \
    uv run --no-project python - <<'PYTHON'
import json
import os
import sys

proc_info = os.environ.get("PROC_INFO", "").strip()
gpu_info = os.environ.get("GPU_INFO", "").strip()
error = os.environ.get("CHECK_ERROR", "").strip()

payload = {"target": os.environ.get("TARGET", "local")}
if error:
    payload["alive"] = None
    payload["error"] = error
    print(json.dumps(payload))
    sys.exit(2)

lines = [line.strip() for line in proc_info.splitlines() if line.strip()]
processes = []
for line in lines:
    parts = line.split(None, 3)
    if len(parts) < 3:
        continue
    processes.append({
        "pid": int(parts[0]) if parts[0].isdigit() else parts[0],
        "stat": parts[1],
        "etime": parts[2],
        "command": parts[3] if len(parts) > 3 else "",
    })

payload["alive"] = any(not p["stat"].startswith("Z") for p in processes)
if lines:
    payload["info"] = lines
    payload["processes"] = processes

if gpu_info:
    gpu_rows = []
    for line in gpu_info.splitlines():
        parts = [p.strip() for p in line.strip().split(",")]
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            continue
        util, mem_used, mem_total = parts
        gpu_rows.append({
            "utilization_gpu_pct": int(util),
            "memory_used_mb": int(mem_used),
            "memory_total_mb": int(mem_total),
        })
    if gpu_rows:
        payload["gpu_stats"] = gpu_rows

print(json.dumps(payload))
PYTHON
