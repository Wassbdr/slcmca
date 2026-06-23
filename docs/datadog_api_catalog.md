# Datadog API catalog — what we can retrieve for slacheck

**Phase 0 deliverable.** This is the supervisor's first ask: *"see what can be retrieved from the
Datadog API"* so we can build a topology graph, extract a critical path, and publish a dashboard.

Cluster: `observit-cluster1`. App: `train-ticket` (services `ts-*`, entrypoint `ts-gateway-service`).
SDK: [`datadog-api-client`](https://github.com/DataDog/datadog-api-client-python) v2.

> This document is written from the published API/SDK shapes. Run `slacheck record` to capture the
> real responses into `fixtures/datadog/` and validate the shapes below.

---

## Live findings (probed 2026-06-23 against `observit-cluster1`)

First contact with the real org. Run `slacheck doctor` then `slacheck record` to reproduce.

| Check | Result | Implication |
|---|---|---|
| `GET /api/v1/validate` (`slacheck doctor`) | ✅ valid | API key + site OK |
| **Site** | `datadoghq.com` (**US**, not EU) | `.env` must use `DD_SITE=datadoghq.com` |
| APM `/api/v1/service_dependencies` | ✅ **200, but empty** (`{}`) for env prod/production/staging/dev/default | `apm_read` GRANTED and working; **no APM trace data visible** |
| APM `/api/v2/services/definitions` | ✅ **0 services** | confirms no traced services in this key's view |
| Software Catalog relations | ✅ reachable but **0 relations** | no declared `dependsOn` either |
| Metrics timeseries (`query_metrics`, `list_active_metrics`) | ❌ **403** | app key lacks `metrics_read` |
| SLOs (`list_slos`) | ❌ **403** | app key lacks `slos_read` |

**Conclusion (revised):** the keys are valid and **`apm_read` is now working**. Two remaining blockers:
1. **No APM data** — the service map and service definitions are *empty* for every env tried. Either
   train-ticket is not emitting APM traces to this org, or it is traced under an account/env this key
   cannot see. This is the **primary** blocker: with no topology there is nothing to build a graph from.
2. **Missing `metrics_read` + `slos_read`** scopes on the app key (still 403). Needed for the SLO values
   even once topology exists.

> Gotcha discovered: the SDK's low-level `call_api` does **not** auto-attach Datadog auth — auth is
> applied inside the *generated* API methods. Raw calls must pass `DD-API-KEY` / `DD-APPLICATION-KEY`
> headers explicitly (fixed in `live_client._service_dependencies_apm`). The earlier "401 on APM" was
> this bug, not a missing scope.

**SDK reality:** `datadog-api-client` 2.56 does **not** ship a `service_dependencies_api`. slacheck
calls the runtime topology endpoint via the SDK's low-level `ApiClient.call_api(...)`, with Software
Catalog `dependsOn` relations as a fallback (see `src/slacheck/datadog/live_client.py`).

---

## Access checklist — what to request from the supervisor

| Item | Why |
|---|---|
| `DD_API_KEY` | org-level API key, every request |
| `DD_APP_KEY` | per-user application key — **carries the permission scopes** |
| `DD_SITE` | **confirmed `datadoghq.com` (US)** for this org (was assumed EU) |
| `DD_ENV` | APM env tag of train-ticket (`prod`/`production`/`staging`) — required param of the deps endpoint |
| scope `apm_read` | service map / service dependencies |
| scope `apm_service_catalog_read` | software catalog (declared dependencies) |
| scope `metrics_read` | timeseries (latency p99, error rate, request rate) |
| scope `slos_read` | existing SLOs |
| scope `monitors_read` | existing monitors |
| scope `dashboards_read` + `dashboards_write` | publish the verdict dashboard (Phase 4) |
| confirm train-ticket emits **APM traces** | the Service Map is built from traces; no traces ⇒ no topology |

---

## 1. Topology — service dependency graph

The graph nodes + edges come from APM. This is the input that replaces the paper's hand-written YAML.

### 1a. Service Dependencies (primary)
- **Endpoint:** `GET /api/v1/service_dependencies?env=<env>` (APM Service Map adjacency)
- **SDK:** ⚠️ no codegen'd class in `datadog-api-client` 2.x. Called via low-level
  `ApiClient.call_api("/api/v1/service_dependencies", "GET", query_params=[("env", env)], ...)`.
  Requires `apm_read` (currently returns 401 — see Live findings).
- **Shape (per service → its downstream calls):**
  ```json
  {
    "ts-gateway-service": { "calls": ["ts-travel-service", "ts-order-service"] },
    "ts-travel-service":  { "calls": ["ts-route-service", "ts-train-service"] },
    "ts-route-service":   { "calls": [] }
  }
  ```
- **→ slacheck:** each `service → callee` becomes a directed edge in `nx.DiGraph`
  (`datadog/topology.py`). Cycles (retries, shared utils) are broken to a DAG in `graph/builder.py`.

### 1b. Software / Service Catalog (enrichment, optional)
- **SDK (v2):** `software_catalog_api.SoftwareCatalogApi.list_catalog_entities()` /
  service definitions `service_definition_api.ServiceDefinitionApi.list_service_definitions()`.
- Gives **declared** `dependsOn`, ownership, tier, links. Used to enrich/validate the runtime map
  when traces are sparse. Not the source of truth for the live graph.

---

## 2. Metrics → Sub-SLO values

Per service, over a window, via timeseries query. These produce the `SloValues` the paper needs.

- **SDK (v2):** `metrics_api.MetricsApi.query_timeseries_data(...)` (POST `/api/v2/query/timeseries`)
  or **(v1):** `metrics_api.MetricsApi.query_metrics(_from=..., to=..., query=...)`
  (GET `/api/v1/query`).

| Paper Sub-SLO | Datadog query (per service `X`) | Conversion |
|---|---|---|
| `response_time_ms` | `p99:trace.http.request.duration{service:X}` (or `trace.servlet.request.duration`) | duration is **ns** → ÷ 1e6 to ms (or s → ×1000) |
| availability inputs | hits: `sum:trace.http.request.hits{service:X}.as_count()` ; errors: `sum:trace.http.request.errors{service:X}.as_count()` | `availability_pct = (1 - errors/hits) * 100` |
| request rate (context) | `sum:trace.http.request.hits{service:X}.as_rate()` | informational + denominator sanity |

> The exact metric namespace depends on train-ticket's instrumentation (`trace.http.request.*`,
> `trace.servlet.request.*`, or OTel `trace.*`). `slacheck record` dumps `slo_list.json` and a sample
> timeseries so we can confirm the real metric names before wiring `datadog/metrics.py`.

**Availability caveat:** `(1 - errors/requests)*100` is a **request-success proxy**, not true uptime.
Surfaced in the verdict and dashboard note.

---

## 3. Existing SLOs & Monitors (reference, not required)
- **SLOs (v1):** `service_level_objectives_api.ServiceLevelObjectivesApi.list_slos()` →
  GET `/api/v1/slo`. Lets us compare *our computed envelope* against SLOs the team already declared.
- **Monitors (v1):** `monitors_api.MonitorsApi.list_monitors()` → GET `/api/v1/monitor`. Context on
  what's alerting; not used in the envelope math.

---

## 4. Infrastructure / Kubernetes (context)
- **Hosts (v1):** `hosts_api.HostsApi.list_hosts()` → GET `/api/v1/hosts`.
- **Container/k8s metrics:** `kubernetes.cpu.usage.total`, `kubernetes.memory.usage` via the metrics
  query above. Relevant for the **operational translation** (paper §IV.D: throughput SLO → CPU>80%
  trigger) — out of scope for the first PoC but the data is available here.

---

## 5. Cost — the gap (do not fake it)
- **Cloud Cost Management (v2):** `cloud_cost_management_api.*` → cloud-bill cost by AWS/GCP/Azure
  account/tag. **This is the cloud invoice, not per-microservice EUR/h.** Mapping a bill line to
  `ts-auth-service` is not something Datadog gives directly, and Cloud Cost may not be enabled on this
  org at all.
- **→ slacheck:** `cost_eur_h` defaults to `None`. The cost operator/fault runs **only** when an
  explicit `cost_overrides.yaml` (per-service EUR/h, hand-supplied like the paper's YAML) is provided.
  Otherwise the verdict states *"cost data unavailable from Datadog; supply overrides to enable cost
  SLO."* This is the honest position the internship should take.

---

## 6. Dashboard publishing (Phase 4)
- **SDK (v1):** `dashboards_api.DashboardsApi.create_dashboard(body=...)` → POST `/api/v1/dashboard`;
  `update_dashboard` for idempotent re-push (search by title first). Needs `dashboards_write`.
- Widgets we push: a **note** widget with the envelope verdict (green/red), a **group** of timeseries
  per critical-path service (reusing the queries in §2), a **group** of fault notes, and a topology
  note. Built as a plain dict in `dashboard/builder.py` (testable offline), pushed by `publisher.py`.

---

## Summary: what maps to what

| slacheck needs | Datadog source | Available? |
|---|---|---|
| graph nodes + edges | Service Dependencies (§1a) | ✅ (needs APM traces) |
| response_time per service | p99 trace duration (§2) | ✅ |
| availability per service | error/hit counts (§2) | ✅ (proxy, not uptime) |
| request rate | trace hits as_rate (§2) | ✅ |
| per-service cost | — | ❌ gap → manual overrides |
| publish dashboard | Dashboards API (§6) | ✅ (needs `dashboards_write`) |
