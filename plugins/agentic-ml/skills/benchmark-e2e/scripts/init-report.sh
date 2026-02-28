#!/usr/bin/env bash
# init-report.sh — scaffold a benchmark report directory for benchmark-e2e
# Usage: init-report.sh [out-dir]

set -euo pipefail

OUT_DIR="${1:-./reports/e2e-benchmark}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="${OUT_DIR}/${TIMESTAMP}"

mkdir -p "${RUN_DIR}/logs"

cat > "${RUN_DIR}/README.md" <<'EOF'
# E2E Benchmark Run

## Matrix

- Harnesses:
- Selected scenario:
- Scenario detection mode:
- Runs per cell:
- Primary metric:

## Results Table

| Harness | Scenario | Quality | Reliability | Efficiency | Ops Readiness | LOC Run | Tokens In | Tokens Out | Tokens Total | Total | Notes |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|

## Recommendation

- Default harness:
- Fallback harness:
- Key risks:
EOF

cat > "${RUN_DIR}/skill-usage-audit.md" <<'EOF'
# Skill Usage Audit

| Harness | Scenario | Expected Skills | Actual Skills | Missing Critical Skills | Notes |
|---|---|---|---|---|---|
EOF

cat > "${RUN_DIR}/run-log.md" <<'EOF'
# Run Log

| Timestamp | Harness | Scenario | Action | Status | LOC Run | Tokens In | Tokens Out | Tokens Total | Artifact |
|---|---|---|---|---|---:|---:|---:|---:|---|
EOF

echo "${RUN_DIR}"
