"""Generate the injected-fault evaluation dataset (paper Table I) as inspectable YAML.

Categories:
- global_slo (10): target exceeds the achievable envelope -> both v1 and v2 detect.
- sub_slo (60): a component's Sub-SLO is below its required threshold.
    * 57 "easy" cases: actual below even the uniform threshold -> v1 AND v2 detect.
    * 3 "gap" cases: a low-centrality component whose actual sits between the (stricter)
      weighted threshold and the (lenient) uniform threshold -> ONLY v2 detects.
- reconfig (43): a transition trigger contradicts the SLO-sustaining predicate -> only v2.
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path("/home/wassimbadraoui/repos/slcmca/fixtures/eval")


def dump(category: str, name: str, doc: dict) -> None:
    (ROOT / category).mkdir(parents=True, exist_ok=True)
    (ROOT / category / f"{name}.yaml").write_text(
        "# Auto-generated evaluation scenario (paper Table I). See scripts/gen_eval.py.\n"
        + yaml.safe_dump(doc, sort_keys=False)
    )


# ---- global_slo: 10 scenarios, target availability above the conjunctive envelope --------
for i in range(1, 11):
    n_comp = 2 + (i % 3)  # 2..4 components
    avail = 99.9
    comps = [{"name": f"c{j}", "slo": {"availability_pct": avail}} for j in range(n_comp)]
    edges = [
        {"source": "c0", "target": f"c{j}", "edge_type": "conjunctive"}
        for j in range(1, n_comp)
    ]
    # envelope = 100 - n*(0.1); pick a target above it -> ascending fault
    target_avail = 100 - 0.05  # 99.95, above the 99.7/99.6 envelope
    dump(
        "global_slo",
        f"global_{i:02d}",
        {
            "entrypoint": "c0",
            "components": comps,
            "edges": edges,
            "global_target": {"availability_pct": target_avail},
            "expected": {"category": "global_slo", "metric": "availability"},
        },
    )

# ---- sub_slo: 57 "easy" + 3 "gap" -------------------------------------------------------
# Easy: 3 components, cost target T; one component's cost exceeds the uniform threshold T/3.
for i in range(1, 58):
    T = 30.0
    # component "big" costs 15 > uniform 10 and > any weighted share -> always a fault
    comps = [
        {"name": "ui", "slo": {"cost_eur_h": 3.0}},
        {"name": "svc", "slo": {"cost_eur_h": 3.0}},
        {"name": "big", "slo": {"cost_eur_h": 15.0}},
    ]
    edges = [
        {"source": "ui", "target": "svc", "edge_type": "conjunctive"},
        {"source": "ui", "target": "big", "edge_type": "conjunctive"},
    ]
    dump(
        "sub_slo",
        f"sub_easy_{i:02d}",
        {
            "entrypoint": "ui",
            "components": comps,
            "edges": edges,
            "global_target": {"cost_eur_h": T},
            "expected": {"category": "sub_slo", "metric": "cost"},
        },
    )

# Gap: low-centrality component (indeg 0) whose actual sits between weighted (strict) and
# uniform (lenient) thresholds -> v1 misses, v2 catches. Storage hub pulls weight away.
for i in range(1, 4):
    T = 40.0
    comps = [
        {"name": "ui", "slo": {"cost_eur_h": 1.0}},
        # actual 5: between weighted 3.64 and uniform 6.67 -> v1 misses, v2 catches
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
            "global_target": {"cost_eur_h": T},
            # the injected fault is on the low-centrality "auth" component
            "expected": {"category": "sub_slo", "metric": "cost"},
            "_note": "heterogeneous-consumption gap: uniform misses, weighted (v2) catches",
        },
    )

# ---- reconfig: 43 scenarios with a contradicting transition trigger ---------------------
for i in range(1, 44):
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
                            "trigger_op": "gt",
                            "trigger_value": 85.0 + (i % 5),  # > 80 -> contradicts the SLO bound
                        }
                    ],
                }
            ],
            "target_slos": ["throughput"],
            "expected": {"category": "reconfig", "metric": "reconfiguration"},
        },
    )

print("generated dataset under", ROOT)
