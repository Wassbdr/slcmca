"""Reconfiguration sustainability under elasticity (paper §III-D).

SLOs are high-level (e.g. throughput); elasticity triggers are low-level operational
parameters (e.g. CPU%). A knowledge base translates the SLO into the operational predicate
that must hold to sustain it (e.g. cpu_pct ≤ 80). A strategy is faulty when a transition's
trigger CONTRADICTS the parameter required to maintain the SLO — which depends on the
action's direction:

- ``scale_up`` adds capacity → lowers the metric (protective). It is faulty only when it
  reacts too late: its trigger fires *exclusively* inside the violating region, i.e. it
  lets the bound be crossed before adding capacity.
- ``scale_down`` removes capacity → raises the metric (risky). It is faulty when its trigger
  region overlaps the violating region: removing capacity while at/over the bound drives the
  metric further past it.
- ``none`` (no protective action): faulty when it can fire inside the violating region.
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


def _violates_required(op: CompareOp, value: float, req_op: CompareOp, req_val: float) -> bool:
    """True if a point satisfying the trigger violates the required predicate."""
    return not _satisfies(req_op, value, req_val)


def _trigger_can_fire_in_violating_region(
    trig_op: CompareOp, trig_val: float, req_op: CompareOp, req_val: float
) -> bool:
    """Does the trigger's satisfied region intersect the SLO-violating region?

    Sampling around both thresholds is exact for the monotone half-line predicates used
    here (gt/ge/lt/le); a scaled epsilon keeps it robust across metric magnitudes.
    """
    eps = max(abs(trig_val), abs(req_val), 1.0) * 1e-9
    probes = (
        trig_val - eps, trig_val, trig_val + eps,
        req_val - eps, req_val, req_val + eps,
    )
    return any(
        _satisfies(trig_op, x, trig_val) and _violates_required(trig_op, x, req_op, req_val)
        for x in probes
    )


def _trigger_only_in_violating_region(
    trig_op: CompareOp, trig_val: float, req_op: CompareOp, req_val: float
) -> bool:
    """Does the trigger fire ONLY where the SLO is already violated (reacts too late)?"""
    eps = max(abs(trig_val), abs(req_val), 1.0) * 1e-9
    probes = (
        trig_val - eps, trig_val, trig_val + eps,
        req_val - eps, req_val, req_val + eps,
    )
    firing = [x for x in probes if _satisfies(trig_op, x, trig_val)]
    if not firing:
        return False
    return all(_violates_required(trig_op, x, req_op, req_val) for x in firing)


def detect_reconfig_faults(
    strategies: Sequence[ReconfigStrategy],
    kb: KnowledgeBase,
    target_slos: Sequence[str],
) -> list[Fault]:
    """Flag transitions whose trigger contradicts the SLO-sustaining predicate, by action."""
    faults: list[Fault] = []
    for strat in strategies:
        for tr in strat.transitions:
            for slo_metric in target_slos:
                rule = translate_slo(kb.translation_rules, slo_metric)
                if rule is None or rule.operational_metric != tr.trigger_metric:
                    continue

                if tr.action == "scale_up":
                    # protective; faulty only if it reacts after the bound is already crossed
                    faulty = _trigger_only_in_violating_region(
                        tr.trigger_op, tr.trigger_value, rule.operational_op, rule.operational_value
                    )
                    why = "adds capacity only after the SLO bound is already exceeded"
                else:
                    # scale_down / none: faulty if it can fire while violating the bound
                    faulty = _trigger_can_fire_in_violating_region(
                        tr.trigger_op, tr.trigger_value, rule.operational_op, rule.operational_value
                    )
                    why = (
                        "removes capacity in a region that violates the SLO bound"
                        if tr.action == "scale_down"
                        else "fires in a violating region with no protective action"
                    )

                if faulty:
                    faults.append(
                        Fault(
                            direction="descending",
                            metric="reconfiguration",
                            component=strat.component,
                            target=rule.operational_value,
                            achievable=tr.trigger_value,
                            message=(
                                f"{strat.name}: transition {tr.from_state}->{tr.to_state} "
                                f"({tr.action}) on {tr.trigger_metric} {tr.trigger_op} "
                                f"{tr.trigger_value:g} {why}; SLO {slo_metric} requires "
                                f"{rule.operational_metric} {rule.operational_op} "
                                f"{rule.operational_value:g}."
                            ),
                        )
                    )
    return faults
