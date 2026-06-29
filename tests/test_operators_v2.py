"""Paper-v2 topology-sensitive operators — exact numbers."""

import pytest

from slacheck.envelope.v2.operators_v2 import (
    agg_availability_conjunctive,
    agg_availability_disjunctive,
    agg_cost_v2,
    agg_latency_conjunctive_paths,
    agg_latency_disjunctive,
)


def test_conjunctive_availability_equals_v1():
    # v2 conjunctive == v1 error-budget: three 99.9% → 99.7%
    assert agg_availability_conjunctive([99.9, 99.9, 99.9]) == pytest.approx(99.7)


def test_disjunctive_availability_improves_with_redundancy():
    # two redundant 99.9% providers → 100 − (0.001 × 0.001)×100 = 99.9999%
    assert agg_availability_disjunctive([99.9, 99.9]) == pytest.approx(99.9999)
    # redundancy must beat any single provider
    assert agg_availability_disjunctive([99.9, 99.9]) > 99.9


def test_cost_is_sum():
    assert agg_cost_v2([8.0, 6.0, 9.0]) == pytest.approx(23.0)


def test_latency_conjunctive_is_max_path():
    assert agg_latency_conjunctive_paths([24.0, 22.0]) == 24.0


def test_latency_disjunctive_is_min_branch():
    assert agg_latency_disjunctive([24.0, 22.0]) == 22.0


def test_empty_inputs_raise():
    with pytest.raises(ValueError):
        agg_availability_conjunctive([])
    with pytest.raises(ValueError):
        agg_availability_disjunctive([])


def test_out_of_range_availability_rejected():
    # garbage-in must not silently produce garbage-out (e.g. 150% availability)
    with pytest.raises(ValueError):
        agg_availability_disjunctive([99.9, 150.0])
    with pytest.raises(ValueError):
        agg_availability_conjunctive([-5.0])
