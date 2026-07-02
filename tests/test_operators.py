"""The paper's worked-example numbers — the load-bearing regression contract (§III-B, §IV)."""

import pytest

from slacheck.envelope.operators import agg_availability, agg_cost, agg_response_time


def test_availability_three_components_99_9_gives_99_7():
    # Paper §V: combining three components at 99.9% yields 99.7% global availability.
    assert agg_availability([99.9, 99.9, 99.9]) == pytest.approx(99.7)


def test_availability_single_component_is_identity():
    assert agg_availability([99.9]) == pytest.approx(99.9)


def test_response_time_is_max_of_path():
    # MaxType: dominated by the slowest component (Auth 14 ms is the max here).
    assert agg_response_time([10.0, 14.0, 12.0]) == 14.0


def test_cost_is_sum():
    assert agg_cost([8.0, 6.0, 9.0]) == pytest.approx(23.0)


def test_empty_inputs_raise():
    with pytest.raises(ValueError):
        agg_availability([])
    with pytest.raises(ValueError):
        agg_response_time([])
