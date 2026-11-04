#!/usr/bin/env bash
# tail-remote.sh — tail a log file on a remote machine over SSH
# Usage: tail-remote.sh user@host /path/to/train.log [N]
#
# Outputs the last N lines (default 100) of the remote log file.
# A leading "~/" in the path is expanded to the remote user's home directory.
# If the file is missing or unreadable, prints an [ERROR] line and exits 0.
# If the SSH connection fails, exits with ssh's status (255).

set -euo pipefail

SSH_TARGET="${1:?Usage: tail-remote.sh user@host /path/to/log [N]}"
REMOTE_PATH="${2:?Missing remote path}"
LINES="${3:-100}"

if ! [[ "$LINES" =~ ^[0-9]+$ ]]; then
    echo "[ERROR] Line count must be a non-negative integer: $LINES" >&2
    exit 1
fi

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

RP="$(rpath "$REMOTE_PATH")"

ssh -n \
    -o ConnectTimeout=10 \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    "$SSH_TARGET" \
    "tail -n ${LINES} -- ${RP} 2>/dev/null || echo '[ERROR] File not found or not readable:' ${RP}"
