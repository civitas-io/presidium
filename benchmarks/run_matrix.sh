#!/usr/bin/env bash
# Drives Apache Bench (a real, separate process/connection per request -- not
# asyncio tasks sharing one connection in the same process as the code under
# test) against a running serve_m7.py instance, across a concurrency matrix,
# for ONE already-loaded rule count (serve_m7.py's rule count is fixed at
# server start -- run this once per rule count, restarting the server between).
#
# Usage:
#   ./run_matrix.sh <base_url> <agent_id> <resource> <output_dir> [n_requests]
#
# Example:
#   ./run_matrix.sh http://100.82.206.105:18080 presidium://bench/bench-agent \
#       tool:benchmark-target results/rules-20 2000

set -euo pipefail

BASE_URL="${1:?base_url required, e.g. http://host:port}"
AGENT_ID="${2:?agent_id required}"
RESOURCE="${3:?resource required, e.g. tool:benchmark-target}"
OUT_DIR="${4:?output_dir required}"
N_REQUESTS="${5:-2000}"

mkdir -p "$OUT_DIR"

PAYLOAD_FILE="$(mktemp)"
printf '{"agent_id": "%s", "action": "%s"}' "$AGENT_ID" "$RESOURCE" > "$PAYLOAD_FILE"
trap 'rm -f "$PAYLOAD_FILE"' EXIT

echo "Payload: $(cat "$PAYLOAD_FILE")"
echo "Target:  ${BASE_URL}/v1/check_grant"
echo

for CONCURRENCY in 1 10 25 50 100; do
    if [ "$CONCURRENCY" -gt "$N_REQUESTS" ]; then
        continue
    fi
    OUT_FILE="${OUT_DIR}/ab_c${CONCURRENCY}.txt"
    echo "=== concurrency=${CONCURRENCY} ==="
    ab -n "$N_REQUESTS" -c "$CONCURRENCY" -p "$PAYLOAD_FILE" -T "application/json" \
        -k "${BASE_URL}/v1/check_grant" > "$OUT_FILE" 2>&1 || {
        echo "ab failed at concurrency=${CONCURRENCY}, see ${OUT_FILE}"
        tail -20 "$OUT_FILE"
        continue
    }
    grep -E "Requests per second|Time per request|Failed requests|50%|66%|75%|80%|90%|95%|98%|99%|100%" "$OUT_FILE"
    echo
done

echo "Raw ab output saved under ${OUT_DIR}/"
