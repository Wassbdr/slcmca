# Running the live Datadog path against another org

The full live loop has been exercised end-to-end on our deployment (topology discovery, live trace
latencies, envelope computation, dashboard publication — see `fixtures/datadog_live/README.md`).
The paper's reproducible case-study numbers still come from the **declared** train-ticket topology
with fixture metrics, because live per-service latency is only as good as the traffic that feeds it
(paper §IV, lesson L3). This file is the runbook for pointing the live path at a **different**
Datadog org — e.g. to replicate the loop on your own cluster.

## 1. Datadog scopes

If the app-key is missing scopes (e.g. **metrics_read / slos_read / dashboards_read /
dashboards_write = 403**), add them to the app-key used in `.env` for your org and site. Then
verify without printing the key:

```bash
slacheck doctor          # must report all scopes green
slacheck explore         # org reconnaissance: which sections are readable, which scopes are missing
```

See `docs/datadog_api_catalog.md` → "Access checklist" for the exact scope names.

## 2. Generate real traffic (so APM sees edges and latency aggregates)

The agent only emits spans for serviced requests; with no traffic the service map is empty and
`trace.servlet.request` (the real Java/Spring trace metric, in **seconds** → converted to ms in
`datadog/live_client.py`) never aggregates. Drive sustained load against the app's entry endpoint
with your load tool of choice (paper §IV, lesson L1 — the default head-based trace sampling needs
both volume and, if necessary, a forced sample rate), then wait ~90s for aggregation.

## 3. Capture, analyse live, publish

```bash
DD_ENV=<your-env> slacheck record --out fixtures/datadog_live       # seed real fixtures
DD_ENV=<your-env> slacheck analyze --source live --paper-version v2 \
    -e ts-ui-dashboard -c latency --service-prefix ts- \
    --exclude-contains with-jaeger                                   # live latency once dense enough
slacheck publish --source live ...                                  # needs dashboards_write
```

If `analyze -c latency` is still sparse (fewer than ~8 services reporting `trace.servlet.request`
duration), generate more successful traffic and re-`record`; this is why the paper's reproducible
latency figures come from the deterministic declared-topology fixtures while the live capture
establishes topological provenance.
