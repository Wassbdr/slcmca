# slacheck

> *What SLA can I commit to?* — compute the **achievable SLA envelope** of a multi-cloud /
> microservices application **from live Datadog topology**, extract a **critical path** under a
> user constraint, detect **over-commitment faults**, and publish a **Datadog dashboard**.

This implements and extends the ISSRE 2026 paper *"What SLA Can I Commit To? Computing Achievable
Service-Level Objectives for Multi-Cloud Applications"*. The paper's `slacheck` works on a
hand-written YAML topology; this tool builds the topology **automatically from Datadog** (cluster
`observit-cluster1`, app `train-ticket`) and presents the result back inside Datadog.

## How it works

```
Datadog APM ──topology──┐
                        ├─► nx.DiGraph ─► critical path ─► envelope ─► verdict ─► Datadog dashboard
Datadog Metrics ─SLOs───┘     (graph/)    (graph/)         (envelope/)            (dashboard/)
```

- **Ascending aggregation** (paper §IV.B): combine per-component Sub-SLOs into the guaranteeable
  global envelope — `max` latency, `sum` cost, error-budget composition for availability.
- **Descending decomposition** (§IV.C): split a target Global-SLO into per-component thresholds.
- **Critical path**: the DAG is reduced to a single **series path** (max-latency or
  min-availability chain) so the paper's series-only operators apply legitimately.

## Quickstart (offline — no Datadog keys needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # paper's numbers are the regression contract
slacheck analyze --source fixture --entrypoint ts-gateway-service --constraint availability
```

## Live mode (requires keys — see docs/datadog_api_catalog.md)

```bash
cp .env.example .env        # fill DD_API_KEY / DD_APP_KEY / DD_SITE / DD_ENV
pip install -e ".[dev,datadog]"
slacheck catalog            # what data Datadog exposes (also a static doc in docs/)
slacheck record             # capture real API responses into fixtures/datadog/
slacheck analyze --source live --entrypoint ts-gateway-service --constraint latency
slacheck publish --source live --entrypoint ts-gateway-service --constraint latency
```

## Reproducing the train-ticket case study

The paper's Real-World Case Study (38 services) is fully reproducible **offline** from the declared
topology + fixture metrics — no credentials:

```bash
python scripts/case_study.py        # emits the v1-vs-v2 numbers + the LaTeX table (tab:casestudy)

# the underlying analyze invocations it runs:
slacheck analyze --source declared --topology fixtures/topology/train-ticket.yaml \
  --metrics-from fixture --paper-version v2 -e ts-ui-dashboard -c availability \
  --min-availability-pct 99.9 --pricing fixtures/scenarios/pricing.example.yaml   # v2: 6 faults, env 98.36%
#   ...same with --paper-version v1 → 3 faults, env 99.40%
#   ...with -c latency --max-latency-ms 30 → v1 feasible (24ms) vs v2 fault (48ms)
```

`tests/test_case_study.py` locks these numbers. The live Datadog path (real APM topology,
provenance only) is documented in [fixtures/datadog_live/README.md](fixtures/datadog_live/README.md).

## Docs

- [docs/datadog_api_catalog.md](docs/datadog_api_catalog.md) — **start here**: what Datadog exposes,
  the exact API calls, metric→SLO conversions, and known gaps.
- [docs/paper_mapping.md](docs/paper_mapping.md) — paper section → code module mapping.
- [CLAUDE.md](CLAUDE.md) — architecture rules, commands, conventions.
