"""Reconfiguration sustainability (paper §III-D), action-direction aware.

A transition is faulty when its trigger contradicts the parameter required to MAINTAIN the
SLO: not merely when it fires in a non-allowed region. A protective scale-up reacting to
high load is correct; a scale-down that can fire near/above the bound is dangerous.
"""

from slacheck.envelope.v2.reconfig import detect_reconfig_faults, translate_slo
from slacheck.models import (
    KnowledgeBase,
    ReconfigStrategy,
    ReconfigTransition,
    SloTranslationRule,
)

# Sustaining throughput requires cpu_pct <= 80.
_RULES = [
    SloTranslationRule(
        slo_metric="throughput",
        operational_metric="cpu_pct",
        operational_op="le",
        operational_value=80.0,
    )
]


def _strategy(action, trigger_op, trigger_value, metric="cpu_pct"):
    return ReconfigStrategy(
        name="autoscale",
        component="Stor",
        transitions=[
            ReconfigTransition(
                from_state="a",
                to_state="b",
                trigger_metric=metric,
                trigger_op=trigger_op,
                trigger_value=trigger_value,
                action=action,
            )
        ],
    )


def _kb():
    return KnowledgeBase(translation_rules=_RULES)


def test_protective_scale_up_is_not_faulty():
    # scale UP when cpu rises toward the limit (gt 75, below 80) → protective, NO fault.
    assert detect_reconfig_faults([_strategy("scale_up", "gt", 75.0)], _kb(), ["throughput"]) == []


def test_late_scale_up_is_faulty():
    # scale UP only after cpu already exceeds the SLO bound (gt 90 > 80) → reacts too late.
    faults = detect_reconfig_faults([_strategy("scale_up", "gt", 90.0)], _kb(), ["throughput"])
    assert len(faults) == 1
    assert faults[0].metric == "reconfiguration"


def test_safe_scale_down_is_not_faulty():
    # scale DOWN only well below the limit (lt 30, safely under 80) → no fault.
    faults = detect_reconfig_faults([_strategy("scale_down", "lt", 30.0)], _kb(), ["throughput"])
    assert faults == []


def test_dangerous_scale_down_is_faulty():
    # scale DOWN can fire at/above the limit (lt 85 overlaps cpu>=80): removing capacity while
    # already over the SLO bound drives the metric further past it.
    faults = detect_reconfig_faults([_strategy("scale_down", "lt", 85.0)], _kb(), ["throughput"])
    assert len(faults) == 1
    assert faults[0].component == "Stor"


def test_metric_mismatch_skipped():
    # trigger on an unrelated operational metric → no rule applies.
    s = _strategy("scale_up", "gt", 90.0, metric="ram_pct")
    assert detect_reconfig_faults([s], _kb(), ["throughput"]) == []


def test_unknown_slo_metric_skipped():
    assert detect_reconfig_faults([_strategy("scale_up", "gt", 90.0)], _kb(), ["latency"]) == []


def test_translate_slo_lookup():
    assert translate_slo(_RULES, "throughput").operational_metric == "cpu_pct"
    assert translate_slo(_RULES, "nope") is None
