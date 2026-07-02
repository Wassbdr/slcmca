"""Sensitivity of the safely-committable envelope A_commit to the confidence factor k (§III-B).

A_commit aggregates margin-adjusted Sub-SLOs ṽᵢ = vᵢ − γᵢ with γᵢ = max(γ_tier, k·σᵢ). The factor
k trades competitiveness against protection: a larger k lowers A_commit (more conservative, safer)
while a smaller k raises it (more competitive, riskier). This study sweeps k over the running
example (three conjunctive 99.9% components with empirical availability stddev) and reports the
resulting A_commit availability, so the paper can show the trade-off as a curve rather than assert
it. It exercises the real compute_commit_envelope_v2 path (no hardcoded envelope numbers).

Reproduce offline (no credentials):
    python scripts/gamma_study.py
"""

from __future__ import annotations

from slacheck.envelope.v2.aggregate_v2 import compute_commit_envelope_v2
from slacheck.models import (
    Component,
    CspProfile,
    DependencyEdge,
    DependencyGraph,
    KnowledgeBase,
    MarginConfig,
    SloValues,
)

# Running example: UI -> Auth, UI -> Stor, all conjunctive, each 99.9% available.
# Each component carries an empirical availability stddev (percentage points) and a CSP tier,
# matching the paper's "historical data available" regime where γ = max(γ_tier, k·σ).
_SIGMA = {"UI": 0.05, "Auth": 0.04, "Stor": 0.06}
_TIER = {"UI": "tier3", "Auth": "tier3", "Stor": "tier2"}
_TIER_FLOOR = {"tier2": 0.02, "tier3": 0.05, "tier4": 0.10}

KS = [0.0, 1.0, 2.0, 3.0, 4.0]


def _graph() -> DependencyGraph:
    comps = {
        n: Component(
            name=n,
            slo=SloValues(availability_pct=99.9),
            csp_profile=CspProfile(tier=_TIER[n], sigma=_SIGMA[n]),
        )
        for n in ("UI", "Auth", "Stor")
    }
    return DependencyGraph(
        components=comps,
        edges=[
            DependencyEdge(source="UI", target="Auth", edge_type="conjunctive"),
            DependencyEdge(source="UI", target="Stor", edge_type="conjunctive"),
        ],
        entrypoint="UI",
    )


def run() -> tuple[list[float], list[float]]:
    """Returns ([k...], [A_commit availability % ...])."""
    g = _graph()
    avail: list[float] = []
    for k in KS:
        kb = KnowledgeBase(margin_config=MarginConfig(k=k, tier_floor=_TIER_FLOOR))
        env = compute_commit_envelope_v2(g, kb)
        avail.append(env.availability_pct)
    return KS, avail


def main() -> None:
    ks, avail = run()
    print("=== A_commit availability vs confidence factor k (running example) ===\n")
    print(f"{'k':>5}{'A_commit avail (%)':>22}")
    for k, a in zip(ks, avail, strict=True):
        print(f"{k:>5.1f}{a:>22.4f}")
    print(f"\nA* (k=0, no margin) = {avail[0]:.4f}% ; "
          f"at k=2 (95% coverage) = {avail[KS.index(2.0)]:.4f}%")


if __name__ == "__main__":
    main()
