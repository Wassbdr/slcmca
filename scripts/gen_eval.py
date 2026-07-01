"""Generate the injected-fault evaluation dataset (paper Table I) as inspectable YAML.

HONESTY NOTE: this is a CONSTRUCTED dataset to demonstrate the *mechanism* by which v2
improves on v1 (typed-DAG operators, weighted decomposition, action-aware reconfiguration),
NOT an empirical benchmark of diverse real systems. The category counts (10/60/43) mirror the
paper; the headline result is that v2 closes the 3 Sub-SLO faults uniform decomposition misses.
Each scenario names the specific injected fault (metric + component + direction) so the harness
checks the RIGHT fault is detected, not just any fault of that metric.

Categories:
- global_slo (10): target exceeds the achievable envelope -> ascending fault (v1 and v2).
- sub_slo (60): a component's Sub-SLO is below its required threshold (descending).
    * 57 "easy" cases (DIVERSIFIED: varied size/metric/values): actual below even the uniform
      threshold -> v1 AND v2 detect.
    * 3 "gap" cases: a low-centrality component whose actual sits between the (stricter)
      weighted threshold and the (lenient) uniform threshold -> ONLY v2 detects.
- reconfig (43): an action-aware faulty elasticity strategy (dangerous scale_down or late
  scale_up) -> only v2 (v1 has no reconfiguration model).
"""
from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "fixtures" / "eval"


def dump(category: str, name: str, doc: dict) -> None:
    (ROOT / category).mkdir(parents=True, exist_ok=True)
    (ROOT / category / f"{name}.yaml").write_text(
        "# Auto-generated evaluation scenario (paper Table I). See scripts/gen_eval.py.\n"
        + yaml.safe_dump(doc, sort_keys=False)
    )


# ---- global_slo: 10 scenarios, target above the conjunctive envelope (ascending fault) ----
for i in range(1, 11):
    n_comp = 2 + (i % 3)  # 2..4 components → varied envelope
    comps = [{"name": f"c{j}", "slo": {"availability_pct": 99.9}} for j in range(n_comp)]
    edges = [
        {"source": "c0", "target": f"c{j}", "edge_type": "conjunctive"}
        for j in range(1, n_comp)
    ]
    target_avail = 99.95  # above the 99.7/99.6 envelope for 2..4 components
    dump(
        "global_slo",
        f"global_{i:02d}",
        {
            "entrypoint": "c0",
            "components": comps,
            "edges": edges,
            "global_target": {"availability_pct": target_avail},
            # whole-path ascending fault → component is None
            "expected": {
                "category": "global_slo",
                "metric": "availability",
                "direction": "ascending",
                "component": None,
            },
        },
    )

# ---- sub_slo: 57 "easy" (DIVERSIFIED) + 3 "gap" -----------------------------------------
# Easy cases: one named "big" component breaches BOTH the uniform (v1) and weighted (v2)
# thresholds, so both versions detect. We compute both thresholds for the actual topology and
# place the offending value strictly beyond the looser of the two, with margin. Varied
# topology size / metric / target keep the scenarios distinct (not clones).
import sys

sys.path.insert(0, str(REPO / "src"))
from slacheck.envelope.decompose import decompose as _decompose_v1  # noqa: E402
from slacheck.envelope.v2.decompose_v2 import decompose_v2 as _decompose_v2  # noqa: E402
from slacheck.models import (  # noqa: E402
    Component,
    DependencyEdge,
    DependencyGraph,
    SloValues,
)

for i in range(1, 58):
    n_extra = i % 4  # 0..3 extra stateless services → 2..5 components
    use_cost = i % 2 == 0
    extras = [f"x{j}" for j in range(n_extra)]
    names = ["ui", *extras, "big"]
    edges = [{"source": "ui", "target": n, "edge_type": "conjunctive"} for n in [*extras, "big"]]

    # build a placeholder graph (slo values filled after thresholds are known) to get weights
    metric = "cost" if use_cost else "availability"
    target_val = 24.0 + (i % 5) if use_cost else 99.9
    target = {"cost_eur_h": target_val} if use_cost else {"availability_pct": target_val}

    g = DependencyGraph(
        components={n: Component(name=n, slo=SloValues()) for n in names},
        edges=[DependencyEdge(**e) for e in edges],
        entrypoint="ui",
    )
    tgt = SloValues(**target)
    thr_v1 = {t.component: t.required for t in _decompose_v1(tgt, names)}
    thr_v2 = {t.component: t.required for t in _decompose_v2(tgt, g)}

    if use_cost:
        looser = max(thr_v1["big"].cost_eur_h, thr_v2["big"].cost_eur_h)
        big_slo = {"cost_eur_h": round(looser + 2.0 + (i % 3), 2)}  # strictly above both
        others = {"cost_eur_h": 1.0}
    else:
        # availability: breach = availability BELOW the stricter (higher) required threshold
        stricter = max(thr_v1["big"].availability_pct, thr_v2["big"].availability_pct)
        big_slo = {"availability_pct": round(stricter - 0.05 - (i % 3) * 0.01, 4)}
        others = {"availability_pct": 99.999}

    comps = (
        [{"name": "ui", "slo": dict(others)}]
        + [{"name": e, "slo": dict(others)} for e in extras]
        + [{"name": "big", "slo": big_slo}]
    )
    dump(
        "sub_slo",
        f"sub_easy_{i:02d}",
        {
            "entrypoint": "ui",
            "components": comps,
            "edges": edges,
            "global_target": target,
            "expected": {
                "category": "sub_slo",
                "metric": metric,
                "direction": "descending",
                "component": "big",
            },
        },
    )

# Gap: low-centrality component (indeg 0) whose actual cost sits between the weighted (strict)
# and uniform (lenient) thresholds -> v1 misses, v2 catches. A storage hub pulls weight away.
for i in range(1, 4):
    comps = [
        {"name": "ui", "slo": {"cost_eur_h": 1.0}},
        # auth actual 5: between weighted 3.64 and uniform 6.67 -> v1 misses, v2 catches
        {"name": "auth", "slo": {"cost_eur_h": 5.0}},
        {"name": "stor", "slo": {"cost_eur_h": 5.0}},
        {"name": "x1", "slo": {"cost_eur_h": 1.0}},
        {"name": "x2", "slo": {"cost_eur_h": 1.0}},
        {"name": "x3", "slo": {"cost_eur_h": 1.0}},
    ]
    edges = [
        {"source": "ui", "target": "stor", "edge_type": "conjunctive"},
        {"source": "x1", "target": "stor", "edge_type": "conjunctive"},
        {"source": "x2", "target": "stor", "edge_type": "conjunctive"},
        {"source": "x3", "target": "stor", "edge_type": "conjunctive"},
        {"source": "auth", "target": "stor", "edge_type": "conjunctive"},
    ]
    dump(
        "sub_slo",
        f"sub_gap_{i:02d}",
        {
            "entrypoint": "ui",
            "components": comps,
            "edges": edges,
            "global_target": {"cost_eur_h": 40.0},
            "expected": {
                "category": "sub_slo",
                "metric": "cost",
                "direction": "descending",
                "component": "auth",  # the low-centrality component uniform under-charges
            },
            "_note": "heterogeneous-consumption gap: uniform misses, weighted (v2) catches",
        },
    )

# ---- reconfig: 43 action-aware faulty strategies ----------------------------------------
# Alternate two genuinely faulty patterns (both contradict cpu_pct <= 80):
#  - dangerous scale_down that can fire at/above the bound (lt V, V > 80),
#  - late scale_up that only reacts after the bound is crossed (gt V, V >= 80).
for i in range(1, 44):
    if i % 2 == 0:
        transition = {
            "trigger_op": "lt",
            "trigger_value": 82.0 + (i % 6),  # lt >80 → can fire while already over the bound
            "action": "scale_down",
        }
    else:
        transition = {
            "trigger_op": "gt",
            "trigger_value": 85.0 + (i % 5),  # gt >=80 → adds capacity only after crossing
            "action": "scale_up",
        }
    dump(
        "reconfig",
        f"reconfig_{i:02d}",
        {
            "entrypoint": "svc",
            "components": [{"name": "svc", "slo": {"availability_pct": 99.9}}],
            "edges": [],
            "knowledge_base": {
                "translation_rules": [
                    {
                        "slo_metric": "throughput",
                        "operational_metric": "cpu_pct",
                        "operational_op": "le",
                        "operational_value": 80.0,
                    }
                ]
            },
            "reconfig_strategies": [
                {
                    "name": f"autoscale_{i}",
                    "component": "svc",
                    "states": [{"name": "a"}, {"name": "b"}],
                    "transitions": [
                        {
                            "from_state": "a",
                            "to_state": "b",
                            "trigger_metric": "cpu_pct",
                            **transition,
                        }
                    ],
                }
            ],
            "target_slos": ["throughput"],
            "expected": {
                "category": "reconfig",
                "metric": "reconfiguration",
                "component": "svc",
            },
        },
    )

print("generated dataset under", ROOT)
