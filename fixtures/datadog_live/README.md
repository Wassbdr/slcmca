# Live Datadog snapshot — train-ticket (provenance artifact)

These JSON files are a **real capture** of the train-ticket microservice as observed through
Datadog APM in the `devolab` org (cluster `observit-cluster1`, namespace `tt-slacheck`). They are
the **provenance evidence** for the paper's case study: they show the dependency topology was
discovered automatically from a live observability backend, not hand-written.

They are **not** used for the reproducible case-study numbers. APM only records edges exercised
during the observation window, so this capture is sparse (≈8 ts-* edges with traffic) and the
per-service latency/availability is volatile. The reproducible figures come from the declared
topology (`fixtures/topology/train-ticket.yaml`, the full documented 85-edge call graph) with
fixture metrics — see `scripts/case_study.py`.

## Consistency with the declared topology

The principal request-path edges observed live agree with the declared graph, e.g.:
`ts-ui-dashboard → ts-travel-service → ts-route-service`,
`ts-travel-service → ts-ticketinfo-service → ts-basic-service → ts-station-service`.
(6 of the 8 live edges are in the declared graph; the 2 extra are direct UI shortcuts.)

## How this was captured

```bash
# .env must have DD_ENV=devolab (the agent tags train-ticket env:devolab, not prod).
# 1) generate traffic (without it APM records no inter-service edges):
kubectl port-forward -n tt-slacheck svc/ts-ui-dashboard 18080:8080 &
#    then loop login + travel queries for ~2-3 min and wait for aggregation, e.g.:
#    POST /api/v1/users/login  {"username":"fdse_microservice","password":"111111"}
#    POST /api/v1/travelservice/trips/left  {"startingPlace":"Shanghai","endPlace":"Suzhou",...}
# 2) capture the real responses into this directory:
DD_ENV=devolab slacheck record --out fixtures/datadog_live
```

`slo_list.json` is absent because the app key lacks the `slos_read` scope (403); the pipeline does
not require it. The k8s resource fixtures (`k8s_*.json`) are large real captures used by the cost
and readiness-availability models.
