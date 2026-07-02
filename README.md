# slacheck

> *What SLA can I commit to?* — compute the **achievable SLA envelope** of a multi-cloud /
> microservices application **from live Datadog topology**, extract a **critical path** under a
> user constraint, detect **over-commitment faults**, and publish a **Datadog dashboard**.

This is the artifact for the ISSRE 2026 industry-track paper *"What SLA Can I Commit To? Computing
Achievable Service-Level Objectives for Multi-Cloud Applications"*. `slacheck` validates an SLA
either on a hand-written YAML topology or by building the topology **automatically from Datadog**
(validated end-to-end on the `train-ticket` benchmark), and presents the result back inside Datadog.

## How it works

```
Datadog APM ──topology──┐
                        ├─► nx.DiGraph ─► critical path ─► envelope ─► verdict ─► Datadog dashboard
Datadog Metrics ─SLOs───┘     (graph/)    (graph/)         (envelope/)            (dashboard/)
```

- **Ascending aggregation** (paper §III-B): combine per-component Sub-SLOs into the guaranteeable
  global envelope — `max` latency, `sum` cost, error-budget composition for availability.
- **Descending decomposition** (§III-C): split a target Global-SLO into per-component thresholds.
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

## Reproducing the empirical evaluation

Everything in `issre_paper.tex` is reproducible **offline**, no credentials. One command runs the
whole thing (datasets → tables → figures) and echoes each paper claim next to the code's output:

```bash
python scripts/reproduce_paper.py     # or: make reproduce
make eval                             # just Table I (tab:eval) as paste-ready LaTeX
```

The individual levels, if you want them one at a time:

```bash
# 1. Real-world case study — train-ticket (38 services), v1 vs v2:
python scripts/case_study.py          # v2: 6 faults / env 98.36%; v1: 3 / 99.40%; latency false-negative
slacheck analyze --source declared --topology fixtures/topology/train-ticket.yaml \
  --metrics-from fixture --paper-version v2 -e ts-ui-dashboard -c availability \
  --min-availability-pct 99.9 --pricing fixtures/scenarios/pricing.example.yaml

# 2. Multiple real systems — train-ticket + Online Boutique (call graph from the GCP manifest):
python scripts/multi_system_study.py  # emits Table tab:realsystems

# 3. Statistical validation — 200 realistic topologies (Alibaba-like distributions, fixed seed):
python scripts/gen_realistic_eval.py 200   # (re)generate the dataset (deterministic)
python scripts/realistic_study.py          # v2 89.5% vs v1 4.0% [Wilson 95% CI], Table tab:realistic
```

Tests lock these numbers: `tests/test_case_study.py` (real systems) and
`tests/test_realistic_study.py` (population). The live Datadog path (real APM topology, provenance
only) is documented in [fixtures/datadog_live/README.md](fixtures/datadog_live/README.md).

## Docs

- [docs/datadog_api_catalog.md](docs/datadog_api_catalog.md) — **start here**: what Datadog exposes,
  the exact API calls, metric→SLO conversions, and known gaps.
- [docs/paper_mapping.md](docs/paper_mapping.md) — paper section → code module mapping.
- [docs/live_unblock.md](docs/live_unblock.md) — runbook for pointing the live path at another org.
