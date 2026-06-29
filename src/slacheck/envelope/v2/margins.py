"""Safety margin γ and the adjusted Sub-SLO ṽᵢ = vᵢ − γᵢ (paper-v2 §IV.C).

γᵢ = max(γ_tier(i), k·σᵢ): the tier classification gives a conservative floor, and the
empirical stddev σᵢ (×k) tightens it when historical data exists. Applying γ at the
Sub-SLO level (before aggregation) localizes each margin where its risk originates and
lets it propagate naturally through the operators, yielding the safely-committable A_commit.
"""

from __future__ import annotations

from slacheck.models import CspProfile, MarginConfig, Metric, SloValues


def gamma(profile: CspProfile | None, config: MarginConfig, metric: Metric) -> float:
    """γ = max(tier_floor, k·σ). Returns 0 when no profile (no margin information)."""
    if profile is None:
        return 0.0
    tier_floor = config.tier_floor.get(profile.tier, 0.0)
    return max(tier_floor, config.k * profile.sigma)


def adjust_slo(slo: SloValues, profile: CspProfile | None, config: MarginConfig) -> SloValues:
    """Return ṽ = v − γ for each present metric. Latency margin makes the bound *stricter*
    by adding the margin (a larger committed latency budget); availability/cost subtract."""
    g_avail = gamma(profile, config, "availability")
    g_lat = gamma(profile, config, "response_time")
    g_cost = gamma(profile, config, "cost")
    return SloValues(
        response_time_ms=(slo.response_time_ms + g_lat)
        if slo.response_time_ms is not None
        else None,
        availability_pct=(slo.availability_pct - g_avail)
        if slo.availability_pct is not None
        else None,
        cost_eur_h=(slo.cost_eur_h + g_cost) if slo.cost_eur_h is not None else None,
    )
