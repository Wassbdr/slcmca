"""Paper-v2 end-to-end evaluation."""

import pytest

from slacheck.envelope.v2.evaluate_v2 import evaluate_v2


def test_full_evaluation_flags_ascending_and_reconfig(paper_scenario_v2):
    s = paper_scenario_v2
    verdict = evaluate_v2(
        s["graph"], s["target"], s["kb"], s["strategies"], s["target_slos"]
    )
    assert verdict.paper_version == "v2"
    assert verdict.commit_envelope is not None
    assert verdict.weights["Auth"] == pytest.approx(2 / 5)

    # 99.999% target exceeds the ~99.59% A_commit → ascending availability fault
    asc = [f for f in verdict.faults if f.direction == "ascending" and f.metric == "availability"]
    assert len(asc) == 1
    assert asc[0].achievable == pytest.approx(verdict.commit_envelope.availability_pct)

    # the faulty autoscale strategy → a reconfiguration fault
    reconf = [f for f in verdict.faults if f.metric == "reconfiguration"]
    assert len(reconf) == 1
    assert not verdict.feasible


def test_evaluation_without_target_reports_envelopes(paper_scenario_v2):
    s = paper_scenario_v2
    verdict = evaluate_v2(s["graph"], target=None, kb=s["kb"])
    assert verdict.faults == []
    assert verdict.envelope.availability_pct == pytest.approx(99.7)
    assert verdict.commit_envelope.availability_pct < 99.7
