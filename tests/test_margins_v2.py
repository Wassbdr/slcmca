"""Paper-v2 safety margin γ and the A_commit envelope."""

import pytest

from slacheck.envelope.v2.aggregate_v2 import compute_commit_envelope_v2, compute_envelope_v2
from slacheck.envelope.v2.margins import gamma
from slacheck.models import CspProfile, MarginConfig


def test_gamma_tier_floor_when_no_history():
    cfg = MarginConfig(k=2.0, tier_floor={"tier3": 0.05})
    # sigma=0 → margin falls back to the tier floor
    assert gamma(CspProfile(tier="tier3", sigma=0.0), cfg, "availability") == pytest.approx(0.05)


def test_gamma_k_sigma_dominates():
    cfg = MarginConfig(k=2.0, tier_floor={"tier1": 0.0})
    # k·σ = 2 × 0.1 = 0.2 exceeds the floor
    assert gamma(CspProfile(tier="tier1", sigma=0.1), cfg, "availability") == pytest.approx(0.2)


def test_gamma_zero_without_profile():
    assert gamma(None, MarginConfig(), "availability") == 0.0


def test_gamma_is_per_metric_no_unit_mixing():
    # the scalar tier_floor/sigma are AVAILABILITY margins (paper's metric). latency/cost get
    # no margin unless their own sigma is supplied — avoids applying 0.05% as 0.05 ms / 0.05 EUR.
    cfg = MarginConfig(k=2.0, tier_floor={"tier3": 0.05})
    prof = CspProfile(tier="tier3", sigma=0.0)
    assert gamma(prof, cfg, "availability") == pytest.approx(0.05)
    assert gamma(prof, cfg, "response_time") == 0.0
    assert gamma(prof, cfg, "cost") == 0.0


def test_gamma_per_metric_sigma_applies():
    cfg = MarginConfig(k=2.0, tier_floor={"tier3": 0.05})
    prof = CspProfile(tier="tier3", sigma=0.0, sigma_latency_ms=1.5, sigma_cost=0.3)
    assert gamma(prof, cfg, "response_time") == pytest.approx(3.0)  # k·σ_lat
    assert gamma(prof, cfg, "cost") == pytest.approx(0.6)  # k·σ_cost


def test_commit_envelope_below_theoretical(paper_scenario_v2):
    graph = paper_scenario_v2["graph"]
    kb = paper_scenario_v2["kb"]
    a_star = compute_envelope_v2(graph).availability_pct
    a_commit = compute_commit_envelope_v2(graph, kb).availability_pct
    assert a_star == pytest.approx(99.7)
    # margins (tier3=0.05 on Auth & Stor, tier2=0.01 on UI) strictly tighten A_commit
    assert a_commit < a_star
    assert a_commit == pytest.approx(99.7 - (0.01 + 0.05 + 0.05))  # 99.59
