# Paper → code mapping

Maps the ISSRE 2026 paper *"What SLA Can I Commit To?"* to slacheck modules. The paper works on a
hand-written YAML topology; slacheck sources the same structure from live Datadog (see
`datadog_api_catalog.md`) and presents the result as a Datadog dashboard.

| Paper concept | Section | Code |
|---|---|---|
| Global-SLA / Sub-SLA, SLOs (response time, availability, cost) | §II.A | `models.py` — `SloValues`, `Component` |
| Dependency graph (UI → Auth, UI → Stor) | §II.B | `graph/builder.py` (`nx.DiGraph`); sourced from Datadog deps |
| Series-only assumption | §IV.A, §VII | `graph/critical_path.py` reduces the DAG to one series path |
| **Ascending** aggregation → guaranteeable envelope | §IV.B | `envelope/aggregate.py` + `envelope/operators.py` |
| — Response time = MaxType `max(vᵢ)` | §IV.B | `operators.agg_response_time` |
| — Cost = SumType `Σ vᵢ` | §IV.B | `operators.agg_cost` |
| — Availability = error-budget `100 − Σ(100 − vᵢ)` | §IV.B | `operators.agg_availability` |
| **Descending** decomposition → per-component thresholds | §IV.C | `envelope/decompose.py` |
| — uniform distribution (known limitation, 3 missed faults) | §VI | documented in `decompose.py` docstring |
| Over-commitment fault (ascending + descending) | §IV.B/C, §I (C1) | `envelope/faults.py` |
| Sustainability under reconfiguration (state machines, KB) | §IV.D | **out of scope for PoC** — data noted in catalog §4 |
| Tool input (YAML schema) | §V | `fixtures/scenarios/paper_example.yaml` (kept as the regression scenario) |
| Tool output (envelope, thresholds, faults) | §V | `models.Verdict`, rendered by `cli.py` and `dashboard/builder.py` |

## Worked example (the regression contract, §II.B + §V)

Three components UI/Auth/Stor, each 99.9% availability:
- envelope availability `= 100 − 3×(100 − 99.9) = 99.7%`.
- architect's target 99.999% > 99.7% → **ascending availability fault** (the paper's headline result).
- Auth latency 14 ms; global target 18 ms.
- cost 23 EUR/h ÷ 3 ≈ 7.67 EUR/h per component (descending).

Encoded in `tests/test_operators.py` and `tests/test_faults.py`.

## Extensions beyond the paper (the internship contribution)

1. **Live topology** from Datadog APM instead of hand-written YAML.
2. **Critical-path extraction** to answer a *specific* user constraint on a real branching DAG
   (the paper only has a 3-node series example).
3. **Datadog dashboard** as the output surface (the paper just prints to stdout).
