# Unblocking the live Datadog path (A5)

The paper's case-study numbers are computed from the **declared** train-ticket topology with fixture
metrics, because (a) live traffic during the observation window was too sparse for per-service
latency to aggregate, and (b) the app-key lacks the scopes needed to read metrics/SLOs and to publish
the dashboard. The pipeline itself runs live (topology discovery works); these two gaps are
operational, not code. This file is the runbook to close them.

## 1. Datadog scopes (supervisor action)

Current app-key returns: APM topology OK, but **metrics_read / slos_read / dashboards_read /
dashboards_write = 403**. Ask the supervisor to add these scopes to the app-key used in `.env`
(org `devolab`, site `datadoghq.com`). Then verify without printing the key:

```bash
slacheck doctor          # must report all scopes green
```

See `docs/datadog_api_catalog.md` → "Access checklist" for the exact scope names.

## 2. Generate real traffic (so APM sees edges and latency aggregates)

The agent only emits spans for serviced requests; with no traffic the service map is empty and
`trace.servlet.request` (the real Java/Spring trace metric, in **seconds** → converted to ms in
`datadog/live_client.py`) never aggregates. Drive a few minutes of load:

```bash
kubectl port-forward -n tt-slacheck svc/ts-ui-dashboard 18080:8080 &
# then loop login + travel queries for ~2-3 min (booking flow exercises the hub services:
# ts-order, ts-station, ts-travel, ts-route, ts-seat), and wait ~90s for aggregation.
```

Do **not** trigger a mass rollout of `tt-slacheck` (42 deploys saturates containerd).

## 3. Capture, analyse live, publish

```bash
DD_ENV=devolab slacheck record --out fixtures/datadog_live          # seed real fixtures
DD_ENV=devolab slacheck analyze --source live --paper-version v2 \
    -e ts-ui-dashboard -c latency --service-prefix ts- \
    --exclude-contains with-jaeger \
    --pricing fixtures/scenarios/pricing.example.yaml                # live latency once dense enough
slacheck publish --source live ...                                  # needs dashboards_write
```

If `analyze -c latency` is still sparse (fewer than ~8 services reporting `trace.servlet.request`
duration), generate more successful traffic and re-`record`; this is why the paper's reproducible
latency figures come from the deterministic declared-topology fixtures while the live capture
establishes topological provenance only.

## 4. What changes in the paper once unblocked

- Replace the §VI-B latency-target sentence's provenance caveat with a live measurement.
- Add the published dashboard URL/screenshot (the JSON is already exported to
  `artifacts/dashboard_train-ticket_devolab.json`, importable via Datadog UI → Import in the
  meantime).
- Soften the §VII "live traffic was sparse" threat accordingly.
