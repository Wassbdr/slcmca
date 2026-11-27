# Raising APM trace sampling on train-ticket

Symptom: `trace.servlet.request` / `trace.spring.handler` aggregate only ~4 points/service even
under load, so p99 dashboards stay near-empty. The instrumentation is active (dd-java-agent injected
via `k8s_lib_injection`), but the tracer's default head-based sampling keeps only a fraction of
traces, and the shared cluster's low successful-request volume compounds it.

Two levers, from least to most invasive.

## 1. Force 100% sampling on the service tracers (per-deployment)

Add these env vars to the train-ticket deployments (they are read by the injected dd-java-agent):

```bash
# apply to one service to validate, then roll out to the rest
kubectl set env -n tt-slacheck deployment/ts-station-service \
  DD_TRACE_SAMPLE_RATE=1 \
  DD_TRACE_RATE_LIMIT=1000

# roll out to all ts-* app deployments (skip -with-jaeger variants):
for d in $(kubectl get deploy -n tt-slacheck -o name | grep -v with-jaeger | grep ts-); do
  kubectl set env -n "tt-slacheck" "$d" DD_TRACE_SAMPLE_RATE=1 DD_TRACE_RATE_LIMIT=1000
done
```

Note: this restarts the pods. Do it in small batches: a simultaneous restart of all ~38
deployments can saturate the container runtime on the shared cluster.

## 2. Agent-side ingestion (if traces are dropped at the Datadog agent)

If the tracers emit but the agent still under-samples, raise the agent's APM sampling target on the
`datadog-agent` DaemonSet (namespace `default`):

```bash
kubectl set env -n default daemonset/datadog-agent \
  DD_APM_MAX_TPS=100 \
  DD_APM_TARGET_TPS=100
```

## 3. Verify

After the pods are back and ~5 min of load has run, check the point density:

```bash
# should now show many points, not ~4
curl -s -G "https://api.<site>/api/v1/query" \
  -H "DD-API-KEY: $DD_API_KEY" -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
  --data-urlencode "from=$(($(date +%s)-900))" --data-urlencode "to=$(date +%s)" \
  --data-urlencode "query=p99:trace.servlet.request{service:ts-station-service}"
```

Then re-`slacheck record` + `slacheck publish` so the dashboard's latency widgets fill in.
