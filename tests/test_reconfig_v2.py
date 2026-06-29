"""Paper-v2 reconfiguration sustainability (§IV.E)."""

from slacheck.envelope.v2.reconfig import detect_reconfig_faults, translate_slo
from slacheck.models import (
    KnowledgeBase,
    ReconfigStrategy,
    ReconfigTransition,
    SloTranslationRule,
)

_RULES = [
    SloTranslationRule(
        slo_metric="throughput",
        operational_metric="cpu_pct",
        operational_op="le",
        operational_value=80.0,
    )
]


def _strategy(trigger_op, trigger_value):
    return ReconfigStrategy(
        name="autoscale",
        component="Stor",
        transitions=[
            ReconfigTransition(
                from_state="a",
                to_state="b",
                trigger_metric="cpu_pct",
                trigger_op=trigger_op,
                trigger_value=trigger_value,
            )
        ],
    )


def test_contradicting_trigger_is_faulty():
    # required cpu <= 80; a transition firing at cpu > 90 occurs in a violating region
    kb = KnowledgeBase(translation_rules=_RULES)
    faults = detect_reconfig_faults([_strategy("gt", 90.0)], kb, ["throughput"])
    assert len(faults) == 1
    assert faults[0].metric == "reconfiguration"
    assert faults[0].component == "Stor"


def test_consistent_trigger_no_fault():
    # firing at cpu < 30 is always within cpu <= 80 → no contradiction
    kb = KnowledgeBase(translation_rules=_RULES)
    assert detect_reconfig_faults([_strategy("lt", 30.0)], kb, ["throughput"]) == []


def test_unknown_slo_metric_skipped():
    kb = KnowledgeBase(translation_rules=_RULES)
    assert detect_reconfig_faults([_strategy("gt", 90.0)], kb, ["latency"]) == []


def test_translate_slo_lookup():
    assert translate_slo(_RULES, "throughput").operational_metric == "cpu_pct"
    assert translate_slo(_RULES, "nope") is None
