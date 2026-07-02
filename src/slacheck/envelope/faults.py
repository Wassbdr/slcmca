"""Over-commitment fault detection (paper §III-B/C) + the top-level evaluate() entry point.

Ascending: the target Global-SLO is stricter than the achievable envelope → structurally
impossible (the paper's headline 99.999% vs 99.7% case).

Descending: a component's measured Sub-SLO falls short of its apportioned threshold.
"""

from __future__ import annotations

from collections.abc import Sequence

from slacheck.envelope.aggregate import compute_envelope
from slacheck.envelope.decompose import decompose
from slacheck.models import Component, Envelope, Fault, SloValues, Threshold, Verdict


def detect_ascending(target: SloValues, envelope: Envelope) -> list[Fault]:
    """Flag global targets the path cannot achieve.

    'Better' direction differs per metric: lower latency/cost is stricter; higher
    availability is stricter. A fault means target is on the stricter side of envelope.
    """
    faults: list[Fault] = []

    if (
        target.response_time_ms is not None
        and envelope.response_time_ms is not None
        and target.response_time_ms < envelope.response_time_ms
    ):
        faults.append(
            Fault(
                direction="ascending",
                metric="response_time",
                component=None,
                target=target.response_time_ms,
                achievable=envelope.response_time_ms,
                message=(
                    f"Target latency {target.response_time_ms:g} ms is below the achievable "
                    f"envelope {envelope.response_time_ms:g} ms on this path."
                ),
            )
        )

    if (
        target.availability_pct is not None
        and envelope.availability_pct is not None
        and target.availability_pct > envelope.availability_pct
    ):
        faults.append(
            Fault(
                direction="ascending",
                metric="availability",
                component=None,
                target=target.availability_pct,
                achievable=envelope.availability_pct,
                message=(
                    f"Target availability {target.availability_pct:g}% exceeds the achievable "
                    f"envelope {envelope.availability_pct:g}% (error budgets compose)."
                ),
            )
        )

    if (
        target.cost_eur_h is not None
        and envelope.cost_eur_h is not None
        and target.cost_eur_h < envelope.cost_eur_h
    ):
        faults.append(
            Fault(
                direction="ascending",
                metric="cost",
                component=None,
                target=target.cost_eur_h,
                achievable=envelope.cost_eur_h,
                message=(
                    f"Target cost {target.cost_eur_h:g} EUR/h is below the achievable "
                    f"envelope {envelope.cost_eur_h:g} EUR/h."
                ),
            )
        )

    return faults


def detect_descending(
    components: Sequence[Component], thresholds: Sequence[Threshold]
) -> list[Fault]:
    """Flag components whose measured Sub-SLO is short of its apportioned threshold."""
    by_name = {t.component: t.required for t in thresholds}
    faults: list[Fault] = []

    for comp in components:
        req = by_name.get(comp.name)
        if req is None:
            continue
        slo = comp.slo

        if (
            req.response_time_ms is not None
            and slo.response_time_ms is not None
            and slo.response_time_ms > req.response_time_ms
        ):
            faults.append(
                Fault(
                    direction="descending",
                    metric="response_time",
                    component=comp.name,
                    target=req.response_time_ms,
                    achievable=slo.response_time_ms,
                    message=(
                        f"{comp.name}: latency {slo.response_time_ms:g} ms exceeds required "
                        f"{req.response_time_ms:g} ms."
                    ),
                )
            )

        if (
            req.availability_pct is not None
            and slo.availability_pct is not None
            and slo.availability_pct < req.availability_pct
        ):
            faults.append(
                Fault(
                    direction="descending",
                    metric="availability",
                    component=comp.name,
                    target=req.availability_pct,
                    achievable=slo.availability_pct,
                    message=(
                        f"{comp.name}: availability {slo.availability_pct:g}% below required "
                        f"{req.availability_pct:g}%."
                    ),
                )
            )

        if (
            req.cost_eur_h is not None
            and slo.cost_eur_h is not None
            and slo.cost_eur_h > req.cost_eur_h
        ):
            faults.append(
                Fault(
                    direction="descending",
                    metric="cost",
                    component=comp.name,
                    target=req.cost_eur_h,
                    achievable=slo.cost_eur_h,
                    message=(
                        f"{comp.name}: cost {slo.cost_eur_h:g} EUR/h exceeds required "
                        f"{req.cost_eur_h:g} EUR/h."
                    ),
                )
            )

    return faults


def evaluate(path: Sequence[Component], target: SloValues | None = None) -> Verdict:
    """Run the full engine over a series ``path``: envelope + (optional) decomposition + faults.

    With no ``target`` the verdict reports just the achievable envelope (the architect's
    primary question, "what *can* I commit to?"). With a ``target`` it also flags ascending
    and descending over-commitment faults.
    """
    envelope = compute_envelope(path)
    notes: list[str] = []
    if envelope.cost_eur_h is None:
        notes.append(
            "Cost data unavailable from Datadog; supply cost_overrides.yaml to enable the cost SLO."
        )
    notes.append(
        "Envelope computed over the critical series path; parallel/redundant branches are not "
        "aggregated (the prior-practice baseline of paper §V), so availability is a "
        "conservative lower bound."
    )

    thresholds: list[Threshold] = []
    faults: list[Fault] = []
    if target is not None:
        thresholds = decompose(target, list(envelope.path))
        faults = detect_ascending(target, envelope) + detect_descending(path, thresholds)

    return Verdict(envelope=envelope, thresholds=thresholds, faults=faults, notes=notes)
