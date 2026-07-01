# Live Datadog snapshot — train-ticket (provenance artifact)

These JSON files are a **real capture** of the train-ticket microservice as observed through
Datadog APM on the test cluster where the benchmark was deployed. They are the **provenance
evidence** for the paper's case study: they show the dependency topology was discovered
automatically from a live observability backend, not hand-written.

They are **not** used for the reproducible case-study numbers. APM only records edges exercised
during the observation window, and several heavy endpoints time out under the shared cluster's
load, so per-service latency/availability is noisy. The reproducible figures come from the declared
topology (`fixtures/topology/train-ticket.yaml`, the full documented 85-edge call graph) with
fixture metrics — see `scripts/case_study.py`.

**The full live loop has been exercised end-to-end**: live topology discovery (38 ts-* services),
live per-service trace latencies (11+ services with data), envelope computation over the typed DAG,
and dashboard publication to Datadog (`slacheck publish --source live`). The published verdict
dashboard: https://datadoghq.com/dashboard/gef-4qb-szk

## Consistency with the declared topology

The principal request-path edges observed live agree with the declared graph, e.g.:
`ts-ui-dashboard → ts-travel-service → ts-route-service`,
`ts-travel-service → ts-ticketinfo-service → ts-basic-service → ts-station-service`.
(6 of the 8 live edges are in the declared graph; the 2 extra are direct UI shortcuts.)

## How this was captured

```bash
# .env must set DD_ENV to whatever the cluster agent tags the app's traces with.
# 1) generate traffic (without it APM records no inter-service edges):
kubectl port-forward -n <namespace> svc/ts-ui-dashboard 18080:8080 &
#    then loop login + travel queries for ~2-3 min and wait for aggregation, e.g.:
#    POST /api/v1/users/login  {"username":"fdse_microservice","password":"111111"}
#    POST /api/v1/travelservice/trips/left  {"startingPlace":"Shanghai","endPlace":"Suzhou",...}
# 2) capture the real responses into this directory:
DD_ENV=<your-env> slacheck record --out fixtures/datadog_live
```

`slo_list.json` is now captured (the `slos_read` scope is granted); the pipeline does not require
it. The k8s resource fixtures (`k8s_*.json`) are large real captures used by the cost and
readiness-availability models.
