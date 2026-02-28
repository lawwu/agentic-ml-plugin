#!/usr/bin/env bash
# fetch-remote-log.sh — fetch a training log and companion config files from a remote machine
# Usage: fetch-remote-log.sh user@host /path/to/run-dir [--lines N] [--out-dir DIR]
#
# Fetches:
#   - The most recent .log file in the run directory
#   - train_args.json, config.json, deepspeed_config.json if present
#   - trainer_state.json (HF Trainer checkpoint metadata) if present
#
# Outputs fetched files to --out-dir (default: ./fetched-logs/<timestamp>/)
# Prints a summary of what was fetched.

set -euo pipefail

SSH_TARGET="${1:?Usage: fetch-remote-log.sh user@host /path/to/run-dir [--lines N] [--out-dir DIR]}"
REMOTE_DIR="${2:?Missing remote run directory}"
LINES=1000
OUT_DIR=""

# Parse optional flags
shift 2
while [[ $# -gt 0 ]]; do
    case "$1" in
        --lines) LINES="$2"; shift 2 ;;
        --out-dir) OUT_DIR="$2"; shift 2 ;;
        *) echo "[WARN] Unknown argument: $1" >&2; shift ;;
    esac
done

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUT_DIR="${OUT_DIR:-./fetched-logs/${TIMESTAMP}}"
mkdir -p "$OUT_DIR"

echo "[fetch-remote-log] Target: ${SSH_TARGET}:${REMOTE_DIR}"
echo "[fetch-remote-log] Output: ${OUT_DIR}"
echo ""

SSH_OPTS="-o ConnectTimeout=15 -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

# Helper: run a remote command silently, return empty string on failure
remote_run() {
    ssh $SSH_OPTS "$SSH_TARGET" "$1" 2>/dev/null || true
}

# 1. Find the most recent log file in the remote directory
REMOTE_LOG="$(remote_run "ls -t '${REMOTE_DIR}'/*.log 2>/dev/null | head -1")"

if [[ -z "$REMOTE_LOG" ]]; then
    # Fall back to any .txt file
    REMOTE_LOG="$(remote_run "ls -t '${REMOTE_DIR}'/*.txt 2>/dev/null | head -1")"
fi

if [[ -n "$REMOTE_LOG" ]]; then
    echo "[fetch-remote-log] Fetching log: ${REMOTE_LOG} (last ${LINES} lines)"
    ssh $SSH_OPTS "$SSH_TARGET" "tail -n ${LINES} '${REMOTE_LOG}'" \
        > "${OUT_DIR}/train.log" 2>/dev/null \
        && echo "  -> ${OUT_DIR}/train.log ($(wc -l < "${OUT_DIR}/train.log") lines)" \
        || echo "  [WARN] Could not fetch log file"
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
    REMOTE_FILE="${REMOTE_DIR}/${fname}"
    EXISTS="$(remote_run "test -f '${REMOTE_FILE}' && echo yes || echo no")"
    if [[ "$EXISTS" == "yes" ]]; then
        scp -q $SSH_OPTS "${SSH_TARGET}:${REMOTE_FILE}" "${OUT_DIR}/${fname}" 2>/dev/null \
            && echo "  -> ${OUT_DIR}/${fname}" \
            || echo "  [WARN] Could not fetch ${fname}"
    fi
done

# 3. List available checkpoints
echo ""
echo "[fetch-remote-log] Checkpoint listing:"
remote_run "ls -td '${REMOTE_DIR}'/checkpoint-* 2>/dev/null | head -10" \
    | while IFS= read -r ckpt; do
        SIZE="$(remote_run "du -sh '${ckpt}' 2>/dev/null | cut -f1")"
        echo "  ${ckpt}  (${SIZE})"
    done || echo "  (none found)"

echo ""
echo "[fetch-remote-log] Done. Files saved to: ${OUT_DIR}"
