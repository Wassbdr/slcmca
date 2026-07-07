# Datadog API catalog — what slacheck reads and writes

Reference for how slacheck maps the paper's inputs to real Datadog endpoints: which calls build the
topology graph, which produce per-service SLO values, where the gaps are, and how the verdict
dashboard is published. Validated against the `train-ticket` benchmark (services `ts-*`, entrypoint
`ts-gateway-service`) using [`datadog-api-client`](https://github.com/DataDog/datadog-api-client-python) v2.

Run `slacheck record` to capture live responses into `fixtures/datadog/` and check them against the
shapes below.

## Status of the live path

The full loop runs live against a real train-ticket deployment: automatic topology discovery
(38 `ts-*` services, ~58 edges), per-service p99 latency, the typed-DAG envelope, and dashboard
publication via `slacheck publish --source live`. Notes worth keeping:

- **APM auth.** The SDK's low-level `call_api` does not attach Datadog auth headers — auth is applied
  inside the generated API methods. Raw calls to the service-dependencies endpoint must pass
  `DD-API-KEY` / `DD-APPLICATION-KEY` explicitly (handled in
  `live_client._service_dependencies_apm`). An early "401 on APM" turned out to be this, not a
  missing scope.
- **Latency metric.** For this Java/Spring app the trace stat is `trace.servlet.request` (its
  duration is the base metric), not `trace.http.request.duration`, and Datadog returns p99 in
  **seconds** — converted to ms at the live edge only (fixtures are already in ms).
- **Why the paper uses declared topology.** APM only records edges exercised during the observation
  window, and several heavy endpoints time out under load, so live per-service metrics are noisy. The
  reproducible case-study numbers therefore come from the declared topology
  (`fixtures/topology/train-ticket.yaml`) with fixture metrics; the JSON in `fixtures/datadog_live/`
  is provenance that the topology is discovered automatically, not hand-written.

Operational steps for pointing this at another org (traffic generation, scopes) are in
`live_unblock.md`.

## Required app-key scopes

The application key carries the permissions; request the scopes matching the features you need.

| Scope | Used for |
|---|---|
| `apm_read` | service map / service dependencies (topology) |
| `apm_service_catalog_read` | software catalog (declared dependencies, enrichment) |
| `metrics_read` | timeseries: latency p99, error rate, request rate |
| `slos_read` | existing SLOs (comparison only) |
| `monitors_read` | existing monitors (context only) |
| `dashboards_read`, `dashboards_write` | publish the verdict dashboard |

The target app must actually emit APM traces — the service map is built from traces, so no traces
means no topology.

## 1. Topology — service dependency graph

Graph nodes and edges come from APM. This replaces the paper's hand-written YAML.

### 1a. Service dependencies (primary)

- Endpoint: `GET /api/v1/service_dependencies?env=<env>` (APM Service Map adjacency).
- `datadog-api-client` 2.x has no generated class for this, so slacheck calls it through the SDK's
  low-level `ApiClient.call_api("/api/v1/service_dependencies", "GET", query_params=[("env", env)], ...)`.
- Shape (per service, its downstream calls):
  ```json
  {
    "ts-gateway-service": { "calls": ["ts-travel-service", "ts-order-service"] },
    "ts-travel-service":  { "calls": ["ts-route-service", "ts-train-service"] },
    "ts-route-service":   { "calls": [] }
  }
  ```
- Each `service → callee` becomes a directed edge in `nx.DiGraph` (`datadog/topology.py`). Cycles
  (retries, shared utilities) are broken into a DAG in `graph/builder.py`.

### 1b. Software catalog (optional enrichment)

- SDK v2: `SoftwareCatalogApi.list_catalog_entities()` / `ServiceDefinitionApi.list_service_definitions()`.
- Gives declared `dependsOn`, ownership, tier, links — used to enrich or validate the runtime map
  when traces are sparse, not as the source of truth for the live graph.

## 2. Metrics — per-service SLO values

Per service, over a window, via timeseries query. These produce the `SloValues` the paper needs.

- SDK v2: `MetricsApi.query_timeseries_data(...)` (POST `/api/v2/query/timeseries`), or v1:
  `MetricsApi.query_metrics(_from=..., to=..., query=...)` (GET `/api/v1/query`).

| Paper Sub-SLO | Datadog query (per service `X`) | Conversion |
|---|---|---|
| `response_time_ms` | `p99:trace.servlet.request{service:X}` (or `trace.http.request.duration`) | seconds → ms (×1000); if a duration is in ns, ÷ 1e6 |
| availability inputs | hits `sum:trace.http.request.hits{service:X}.as_count()`, errors `sum:trace.http.request.errors{service:X}.as_count()` | `availability_pct = (1 - errors/hits) * 100` |
| request rate (context) | `sum:trace.http.request.hits{service:X}.as_rate()` | informational, denominator sanity check |

The exact namespace depends on the app's instrumentation (`trace.http.request.*`,
`trace.servlet.request.*`, or OTel `trace.*`); `slacheck record` dumps a sample timeseries so the
real metric names can be confirmed before wiring `datadog/metrics.py`.

Availability here is `(1 - errors/requests) * 100` — a request-success proxy, not true uptime. This
is surfaced in the verdict and the dashboard note.

## 3. Existing SLOs and monitors (reference only)

- SLOs (v1): `ServiceLevelObjectivesApi.list_slos()` (GET `/api/v1/slo`) — lets slacheck compare its
  computed envelope against SLOs the team already declared.
- Monitors (v1): `MonitorsApi.list_monitors()` (GET `/api/v1/monitor`) — context on what is alerting;
  not used in the envelope math.

## 4. Cost — the gap and the stand-in

Datadog does not expose per-microservice cost. Cloud Cost Management (`cloud_cost_management_api.*`)
returns the cloud bill by account/tag, not a per-service EUR/h, and mapping a bill line to a service
is not something the API provides. slacheck never fabricates a cost:

- **Declared overrides (exact).** `cost_overrides.yaml` (per-service EUR/h, hand-supplied like the
  paper's YAML) via `--cost-overrides`.

`cost_eur_h` stays `None` unless `--cost-overrides` is given.

## 5. Dashboard publishing

- SDK v1: `DashboardsApi.create_dashboard(body=...)` (POST `/api/v1/dashboard`), with
  `update_dashboard` for idempotent re-push (search by title first). Needs `dashboards_write`.
- Widgets: a note with the envelope verdict, a group of per-service timeseries (reusing the §2
  queries), a group of fault notes, and a topology note. Built as a plain dict in
  `dashboard/builder.py` (testable offline), pushed by `publisher.py`.

## Summary

| slacheck needs | Datadog source | Available? |
|---|---|---|
| graph nodes + edges | service dependencies (§1a) | yes (needs APM traces) |
| response time per service | p99 trace duration (§2) | yes |
| availability per service | error/hit counts (§2) | yes (success proxy, not uptime) |
| request rate | trace hits as_rate (§2) | yes |
| per-service cost | — | no direct source (§4 stand-in) |
| publish dashboard | Dashboards API (§5) | yes (needs `dashboards_write`) |
