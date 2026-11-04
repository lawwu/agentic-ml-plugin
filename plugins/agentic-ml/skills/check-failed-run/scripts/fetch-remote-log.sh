#!/usr/bin/env bash
# fetch-remote-log.sh — fetch a training log and companion config files from a remote machine
# Usage: fetch-remote-log.sh user@host /path/to/run-dir [--lines N] [--out-dir DIR]
#
# Fetches:
#   - The most recent .log file in the run directory (falls back to .txt)
#   - train_args.json, config.json, deepspeed_config.json if present
#   - trainer_state.json (HF Trainer checkpoint metadata) if present
#
# A leading "~/" in the run directory is expanded to the remote user's home.
# Outputs fetched files to --out-dir (default: ./fetched-logs/<timestamp>/)
# Prints a summary of what was fetched. Exits 2 if the host is unreachable.

set -euo pipefail

SSH_TARGET="${1:?Usage: fetch-remote-log.sh user@host /path/to/run-dir [--lines N] [--out-dir DIR]}"
REMOTE_DIR="${2:?Missing remote run directory}"
LINES=1000
OUT_DIR=""

# Parse optional flags
shift 2
while [[ $# -gt 0 ]]; do
    case "$1" in
        --lines) LINES="${2:?--lines requires a value}"; shift 2 ;;
        --out-dir) OUT_DIR="${2:?--out-dir requires a value}"; shift 2 ;;
        *) echo "[WARN] Unknown argument: $1" >&2; shift ;;
    esac
done

if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] --lines must be a non-negative integer: $LINES" >&2
    exit 1
fi

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUT_DIR:-./fetched-logs/${TIMESTAMP}}"
mkdir -p "$OUT_DIR"

echo "[fetch-remote-log] Target: ${SSH_TARGET}:${REMOTE_DIR}"
echo "[fetch-remote-log] Output: ${OUT_DIR}"
echo ""

SSH_OPTS=(-n -o ConnectTimeout=15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new)

# Single-quote a string for the remote POSIX shell.
sq() { printf "'%s'" "$(printf '%s' "$1" | sed "s/'/'\\\\''/g")"; }
# Quote a remote path, keeping a leading ~/ expandable.
rpath() {
    if [[ "$1" == "~/"* ]]; then
        printf '"$HOME"/%s' "$(sq "${1#\~/}")"
    else
        sq "$1"
    fi
}

# Run a remote command; -n keeps ssh from consuming the caller's stdin.
remote_run() {
    ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "$1" 2>/dev/null || true
}

if ! ssh "${SSH_OPTS[@]}" "$SSH_TARGET" true 2>/dev/null; then
    echo "[ERROR] Cannot connect to ${SSH_TARGET} (check host, keys, and network)" >&2
    exit 2
fi

RD="$(rpath "$REMOTE_DIR")"

# 1. Find the most recent log file in the remote directory
REMOTE_LOG="$(remote_run "ls -t -- ${RD}/*.log 2>/dev/null | head -n 1")"

if [[ -z "$REMOTE_LOG" ]]; then
    # Fall back to any .txt file
    REMOTE_LOG="$(remote_run "ls -t -- ${RD}/*.txt 2>/dev/null | head -n 1")"
fi

if [[ -n "$REMOTE_LOG" ]]; then
    echo "[fetch-remote-log] Fetching log: ${REMOTE_LOG} (last ${LINES} lines)"
    if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "tail -n ${LINES} -- $(sq "$REMOTE_LOG")" \
        > "${OUT_DIR}/train.log" 2>/dev/null; then
        echo "  -> ${OUT_DIR}/train.log ($(wc -l < "${OUT_DIR}/train.log" | tr -d ' ') lines)"
    else
        echo "  [WARN] Could not fetch log file"
    fi
else
    echo "[WARN] No .log or .txt file found in ${REMOTE_DIR}"
fi

# 2. Fetch companion config files
COMPANION_FILES=(
    "train_args.json"
    "training_args.json"
    "config.json"
    "deepspeed_config.json"
    "trainer_state.json"
    "all_results.json"
)

for fname in "${COMPANION_FILES[@]}"; do
    REMOTE_FILE="${RD}/$(sq "$fname")"
    EXISTS="$(remote_run "test -f ${REMOTE_FILE} && echo yes || echo no")"
    if [[ "$EXISTS" == "yes" ]]; then
        if ssh "${SSH_OPTS[@]}" "$SSH_TARGET" "cat -- ${REMOTE_FILE}" > "${OUT_DIR}/${fname}" 2>/dev/null; then
            echo "  -> ${OUT_DIR}/${fname}"
        else
            rm -f "${OUT_DIR}/${fname}"
            echo "  [WARN] Could not fetch ${fname}"
        fi
    fi
done

# 3. List available checkpoints (sizes computed in the same remote call)
echo ""
echo "[fetch-remote-log] Checkpoint listing:"
CKPT_CMD="ls -td -- ${RD}/checkpoint-* 2>/dev/null | head -n 10 | "'while IFS= read -r d; do printf "%s\t%s\n" "$d" "$(du -sh -- "$d" 2>/dev/null | cut -f1)"; done'
CKPTS="$(remote_run "$CKPT_CMD")"
if [[ -n "$CKPTS" ]]; then
    while IFS=$'\t' read -r ckpt size; do
        echo "  ${ckpt}  (${size})"
    done <<<"$CKPTS"
else
    echo "  (none found)"
fi

echo ""
echo "[fetch-remote-log] Done. Files saved to: ${OUT_DIR}"
