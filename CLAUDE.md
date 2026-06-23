# CLAUDE.md — slacheck

Guidance for Claude Code (and humans) working in this repo. Keep this file lean; put detail in `docs/`.

## What this is

`slacheck` computes the **achievable SLA envelope** of a microservices app **from live Datadog
topology**, extracts a **critical path** answering a user's SLA constraint, detects
**over-commitment faults**, and publishes a **Datadog dashboard**. It implements and extends the
ISSRE 2026 paper *"What SLA Can I Commit To?"*. Paper→code mapping: `docs/paper_mapping.md`.

## Architecture rule (do not break)

**Layered, dependency-inverted.** The math core is pure; Datadog is an I/O adapter at the edge.

- `src/slacheck/envelope/` — **pure math** (paper §IV). **MUST NOT import `slacheck.datadog`** or any
  Datadog SDK. It operates only on `models.py` types. This is what makes it unit-testable against the
  paper's worked example and runnable offline.
- `src/slacheck/datadog/` — all Datadog I/O lives behind the `DatadogSource` protocol in `source.py`.
  Two backends: `live_client.py` (real API) and `fixture_client.py` (replays `fixtures/datadog/*.json`).
- `src/slacheck/graph/` — `nx.DiGraph` topology + `critical_path.py` reduces the branching DAG to one
  **series path** so the paper's series-only operators apply legitimately (paper limitation §VII).
- `src/slacheck/models.py` — pydantic v2 data contracts shared across all layers (Datadog-agnostic).
- `src/slacheck/dashboard/` — builds Datadog dashboard JSON (`builder.py`, pure dict, testable) and
  pushes it (`publisher.py`).

The whole pipeline (topology → graph → critical path → envelope → dashboard JSON) runs **offline on
fixtures** with no credentials. Live Datadog is only needed to refresh fixtures and publish.

## Paper fidelity = regression contract

The aggregation operators encode the paper exactly. The worked example is the non-regression test:
- `agg_availability([99.9, 99.9, 99.9]) ≈ 99.7` (paper §V).
- cost `23 EUR/h / 3 ≈ 7.67` per component (§IV.C / §VI).
- Auth latency 14 ms vs global target 18 ms; 99.999% target vs 99.7% envelope → ascending fault.

**Do not change `envelope/operators.py` without updating `tests/test_operators.py`.**

## Commands

```bash
pip install -e ".[dev]"            # offline dev (no Datadog SDK)
pip install -e ".[dev,datadog]"    # + live Datadog integration
pytest                             # offline tests (live tests skipped by default)
pytest -m live                     # live smoke tests (needs DD_API_KEY)
ruff check . && mypy               # lint + types
slacheck analyze --source fixture --entrypoint ts-gateway-service --constraint availability
slacheck record                    # capture real API responses → fixtures/ (needs keys)
slacheck publish --source live ... # push dashboard (needs dashboards_write)
```

`--source fixture` is the default for dev; `--source live` requires `.env`.

## Secrets

Never hardcode keys. Never paste real keys into chat or commits. Copy `.env.example` → `.env`
(gitignored), loaded by `config.py` (`pydantic-settings`). What to request from the supervisor and
the required scopes are in `docs/datadog_api_catalog.md` ("Access checklist").

## Conventions

- pydantic v2 models in `models.py`; `networkx.DiGraph`; `typer` CLI; `ruff` + `mypy`.
- Datadog cannot give per-service **cost** (Cloud Cost = cloud bill, not per-microservice). `cost_eur_h`
  defaults to `None`; cost SLO only runs when an explicit `cost_overrides.yaml` is supplied. Never fake it.
- Availability is derived as `(1 - errors/requests) * 100` — a request-success proxy, not true uptime.
  Both caveats are surfaced in the verdict and the catalog.

## For a fresh Claude session

1. Read `docs/datadog_api_catalog.md` (what Datadog exposes, conversions, gaps).
2. Work offline against `fixtures/` first.
3. Run `pytest` before touching live.

## Status

- Phase 0 (catalog + scaffold), Phase 1 (envelope engine), Phase 2 (graph + critical path on
  fixtures), Phase 4 (dashboard builder) are buildable/testable **offline**.
- Phase 3 (live integration) is **blocked on Datadog keys** — see the access checklist. Once keys
  arrive: `slacheck record` to seed real fixtures, then validate parsing against real shapes.
