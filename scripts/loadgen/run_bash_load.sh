#!/bin/bash
# Sustained bash load generator for train-ticket (no gevent/locust dependency).
# Feeds Datadog APM continuously so trace.servlet.request / trace.spring.handler aggregate
# a real p99 per service. Run alongside a port-forward:
#   kubectl port-forward -n tt-slacheck svc/ts-ui-dashboard 18080:8080 &
#   scripts/loadgen/run_bash_load.sh 1800   # seconds (default 1200)
set -u
BASE="${BASE:-http://localhost:18080}"
DURATION="${1:-1200}"
CONCURRENCY="${CONCURRENCY:-6}"
END=$(( $(date +%s) + DURATION ))

worker() {
  while [ "$(date +%s)" -lt "$END" ]; do
    T=$(curl -s --max-time 4 -X POST "$BASE/api/v1/users/login" \
        -H "Content-Type: application/json" -d '{"username":"fdse_microservice","password":"111111"}' \
        | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
    A="Authorization: Bearer $T"
    curl -s -o /dev/null --max-time 4 "$BASE/api/v1/stationservice/stations" -H "$A"
    curl -s -o /dev/null --max-time 4 "$BASE/api/v1/trainservice/trains" -H "$A"
  done
}

echo "load: ${CONCURRENCY} workers for ${DURATION}s against ${BASE}"
for _ in $(seq "$CONCURRENCY"); do worker & done
wait
echo "load finished"
