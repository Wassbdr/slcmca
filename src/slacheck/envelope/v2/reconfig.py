"""Reconfiguration sustainability under elasticity (paper-v2 §IV.E).

SLOs are high-level (e.g. throughput); elasticity triggers are low-level operational
parameters (e.g. CPU%). A knowledge base translates the SLO into the operational predicate
that must hold to sustain it. A strategy is faulty when a transition trigger can fire in a
region that violates that predicate — i.e. the trigger's satisfied region is not contained
in the region the SLO requires.
"""

from __future__ import annotations

from collections.abc import Sequence

from slacheck.models import (
    CompareOp,
    Fault,
    KnowledgeBase,
    ReconfigStrategy,
    SloTranslationRule,
)


def translate_slo(
    rules: Sequence[SloTranslationRule], slo_metric: str
) -> SloTranslationRule | None:
    """Return the operational predicate that sustains ``slo_metric``, or None if unknown."""
    return next((r for r in rules if r.slo_metric == slo_metric), None)


def _satisfies(op: CompareOp, value: float, bound: float) -> bool:
    if op == "gt":
        return value > bound
    if op == "ge":
        return value >= bound
    if op == "lt":
        return value < bound
    return value <= bound  # le


def _trigger_region_within_required(
    trig_op: CompareOp, trig_val: float, req_op: CompareOp, req_val: float
) -> bool:
    """Is every point where the trigger fires also a point the required predicate allows?

    Sampling-based containment over the relevant boundary points — exact for the
    monotone half-line predicates used here (gt/ge/lt/le).
    """
    # Probe points around both thresholds capture all qualitative regions of two half-lines.
    eps = 1e-6
    probes = {
        trig_val - eps, trig_val, trig_val + eps,
        req_val - eps, req_val, req_val + eps,
    }
    for x in probes:
        if _satisfies(trig_op, x, trig_val) and not _satisfies(req_op, x, req_val):
            return False
    return True


def detect_reconfig_faults(
    strategies: Sequence[ReconfigStrategy],
    kb: KnowledgeBase,
    target_slos: Sequence[str],
) -> list[Fault]:
    """Flag transitions whose trigger contradicts the SLO-sustaining operational predicate."""
    faults: list[Fault] = []
    for strat in strategies:
        for tr in strat.transitions:
            for slo_metric in target_slos:
                rule = translate_slo(kb.translation_rules, slo_metric)
                if rule is None or rule.operational_metric != tr.trigger_metric:
                    continue
                if not _trigger_region_within_required(
                    tr.trigger_op, tr.trigger_value, rule.operational_op, rule.operational_value
                ):
                    faults.append(
                        Fault(
                            direction="descending",
                            metric="reconfiguration",
                            component=strat.component,
                            target=rule.operational_value,
                            achievable=tr.trigger_value,
                            message=(
                                f"{strat.name}: transition {tr.from_state}->{tr.to_state} fires on "
                                f"{tr.trigger_metric} {tr.trigger_op} {tr.trigger_value:g}, which "
                                f"violate the {slo_metric} SLO requirement "
                                f"{rule.operational_metric} {rule.operational_op} "
                                f"{rule.operational_value:g}."
                            ),
                        )
                    )
    return faults
