#!/usr/bin/env bash
# tail-remote.sh — tail a log file on a remote machine over SSH
# Usage: tail-remote.sh user@host /path/to/train.log [N]
#
# Outputs the last N lines (default 100) of the remote log file.
# Exits cleanly if the connection fails or file does not exist.

set -euo pipefail

SSH_TARGET="${1:?Usage: tail-remote.sh user@host /path/to/log [N]}"
REMOTE_PATH="${2:?Missing remote path}"
LINES="${3:-100}"

ssh -o ConnectTimeout=10 \
    -o BatchMode=yes \
    -o StrictHostKeyChecking=accept-new \
    "$SSH_TARGET" \
    "tail -n $LINES '$REMOTE_PATH' 2>/dev/null || echo '[ERROR] File not found or not readable: $REMOTE_PATH'"
