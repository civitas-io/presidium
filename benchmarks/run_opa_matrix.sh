#!/usr/bin/env bash
# Same ab-driven matrix as run_matrix.sh, against a real `opa run --server`
# instance's /v1/data/<policy>/allow endpoint instead of Presidium's
# /v1/check_grant -- the one real, fair, same-hardware comparison point
# identified in docs/design/performance-research.md.
#
# Usage:
#   ./run_opa_matrix.sh <base_url> <policy_path> <output_dir> [n_requests]
#
# Example:
#   ./run_opa_matrix.sh http://localhost:8181 bench/allow results/opa-rules-20 800

set -euo pipefail

BASE_URL="${1:?base_url required}"
POLICY_PATH="${2:?policy_path required, e.g. bench/allow}"
OUT_DIR="${3:?output_dir required}"
N_REQUESTS="${4:-800}"

mkdir -p "$OUT_DIR"

PAYLOAD_FILE="$(mktemp)"
printf '{"input": {"resource": "tool:benchmark-target"}}' > "$PAYLOAD_FILE"
trap 'rm -f "$PAYLOAD_FILE"' EXIT

echo "Payload: $(cat "$PAYLOAD_FILE")"
echo "Target:  ${BASE_URL}/v1/data/${POLICY_PATH}"
echo

for CONCURRENCY in 1 10 25 50 100; do
    if [ "$CONCURRENCY" -gt "$N_REQUESTS" ]; then
        continue
    fi
    OUT_FILE="${OUT_DIR}/ab_c${CONCURRENCY}.txt"
    echo "=== concurrency=${CONCURRENCY} ==="
    ab -n "$N_REQUESTS" -c "$CONCURRENCY" -p "$PAYLOAD_FILE" -T "application/json" \
        -k "${BASE_URL}/v1/data/${POLICY_PATH}" > "$OUT_FILE" 2>&1 || {
        echo "ab failed at concurrency=${CONCURRENCY}, see ${OUT_FILE}"
        tail -20 "$OUT_FILE"
        continue
    }
    grep -E "Requests per second|Time per request|Failed requests|50%|95%|99%|100%" "$OUT_FILE"
    echo
done

echo "Raw ab output saved under ${OUT_DIR}/"
