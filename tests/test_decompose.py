"""Descending decomposition (paper §IV.C): cost/n and error-budget split."""

import pytest

from slacheck.envelope.decompose import decompose
from slacheck.models import SloValues


def test_cost_split_evenly(paper_scenario):
    thresholds = decompose(paper_scenario["global_target"], ["UI", "Auth", "Stor"])
    assert len(thresholds) == 3
    # Paper §VI: 23 EUR/h / 3 = 7.67 per component.
    assert thresholds[0].required.cost_eur_h == pytest.approx(23.0 / 3)
    assert thresholds[0].required.cost_eur_h == pytest.approx(7.6667, abs=1e-3)


def test_availability_budget_split():
    # Global 99.999% -> budget 0.001%, split across 3 -> each must reach 100 - 0.001/3.
    thresholds = decompose(SloValues(availability_pct=99.999), ["a", "b", "c"])
    expected = 100.0 - (0.001 / 3)
    assert thresholds[0].required.availability_pct == pytest.approx(expected)


def test_latency_not_divided():
    # MaxType: each component must individually meet the global latency (not /n).
    thresholds = decompose(SloValues(response_time_ms=18.0), ["a", "b"])
    assert thresholds[0].required.response_time_ms == 18.0
    assert thresholds[1].required.response_time_ms == 18.0


def test_empty_components_raise():
    with pytest.raises(ValueError):
        decompose(SloValues(cost_eur_h=10), [])
