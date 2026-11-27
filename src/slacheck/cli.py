"""slacheck CLI (typer). Offline-first: --source fixture is the default.

Commands:
  analyze   run the pipeline and print envelope + faults (fixture or live)
  check     check a self-contained topology YAML against a target SLO (v1 and/or v2)
  eval      reproduce the fault-detection table (v1 vs v2) on the injected-fault dataset
  publish   build the dashboard and push it to Datadog (live, needs dashboards_write)
  record    capture live API responses into fixtures/datadog/ (live, needs keys)
  catalog   point to the Datadog API catalog doc
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from slacheck.availability import check_availability
from slacheck.config import Settings
from slacheck.datadog.source import get_source
from slacheck.graph.trace_import import TraceSource, load_trace_graph
from slacheck.models import SloValues
from slacheck.openslo import load_openslo_target
from slacheck.pipeline import AnalysisResult, analyze

app = typer.Typer(add_completion=False, help="Achievable SLA envelope from Datadog topology.")

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REPO_EVAL = _REPO_ROOT / "fixtures" / "eval"
# Source checkout first; a regular `pip install .` ships the same files as slacheck/eval_fixtures.
_EVAL_DATASET = _REPO_EVAL if _REPO_EVAL.is_dir() else Path(__file__).parent / "eval_fixtures"


def _apply_cost_overrides(result: AnalysisResult, path_file: Path | None) -> None:
    """Inject per-service EUR/h from a YAML override file into the path components in place.

    Datadog has no per-service cost (catalog §5); this is the only honest way to enable
    the cost SLO. File shape: ``{service_name: eur_per_hour}``.
    """
    if path_file is None:
        return
    overrides = yaml.safe_load(path_file.read_text()) or {}
    for comp in result.path:
        if comp.name in overrides:
            comp.slo = comp.slo.model_copy(update={"cost_eur_h": float(overrides[comp.name])})


def _build_target(
    max_latency_ms: float | None,
    min_availability_pct: float | None,
    max_cost_eur_h: float | None,
) -> SloValues | None:
    if max_latency_ms is None and min_availability_pct is None and max_cost_eur_h is None:
        return None
    return SloValues(
        response_time_ms=max_latency_ms,
        availability_pct=min_availability_pct,
        cost_eur_h=max_cost_eur_h,
    )


def _render(result: AnalysisResult) -> None:
    v = result.verdict
    env = v.envelope
    typer.echo(f"\nEntrypoint : {result.entrypoint}")
    typer.echo(f"Constraint : {result.constraint}")
    typer.echo(f"Paper version : {result.paper_version}")
    label = "Topological order" if result.paper_version == "v2" else "Critical path"
    typer.echo(f"{label} : {' -> '.join(env.path)}")
    typer.echo("\nAchievable envelope (A*):")
    typer.echo(f"  latency      : {env.response_time_ms!r} ms")
    typer.echo(f"  availability : {env.availability_pct!r} %")
    typer.echo(f"  cost         : {env.cost_eur_h!r} EUR/h")

    if v.commit_envelope is not None:
        ce = v.commit_envelope
        typer.echo("\nSafely committable envelope (A_commit, after γ margins):")
        typer.echo(f"  latency      : {ce.response_time_ms!r} ms")
        typer.echo(f"  availability : {ce.availability_pct!r} %")
        typer.echo(f"  cost         : {ce.cost_eur_h!r} EUR/h")
    if v.weights:
        typer.echo("\nStructural weights (wᵢ):")
        for name, w in v.weights.items():
            typer.echo(f"  {name}: {w:.4f}")

    if v.faults:
        typer.secho(f"\nOVER-COMMITMENT FAULTS ({len(v.faults)}):", fg=typer.colors.RED, bold=True)
        for f in v.faults:
            typer.secho(f"  [{f.direction}/{f.metric}] {f.message}", fg=typer.colors.RED)
    else:
        typer.secho("\nNo over-commitment faults. ✅", fg=typer.colors.GREEN)

    if v.notes:
        typer.echo("\nNotes:")
        for n in v.notes:
            typer.echo(f"  - {n}")


@app.command(name="analyze")
def analyze_cmd(
    entrypoint: str = typer.Option(..., "--entrypoint", "-e", help="Entrypoint service."),
    constraint: str = typer.Option("latency", "--constraint", "-c", help="latency | availability"),
    source: str = typer.Option("fixture", "--source", help="fixture | live | declared"),
    topology: Path | None = typer.Option(None, help="Topology YAML (for --source declared)."),
    metrics_from: str = typer.Option("fixture", help="declared source: live | fixture metrics."),
    paper_version: str = typer.Option("v1", "--paper-version", help="v1 | v2"),
    sink: str | None = typer.Option(None, "--sink", help="Optional target/sink service."),
    max_latency_ms: float | None = typer.Option(None, help="Global target: max latency (ms)."),
    min_availability_pct: float | None = typer.Option(None, help="Global target: min avail (%)."),
    max_cost_eur_h: float | None = typer.Option(None, help="Global target: max cost (EUR/h)."),
    cost_overrides: Path | None = typer.Option(None, help="YAML of per-service EUR/h (exact)."),
    pricing: Path | None = typer.Option(None, help="YAML cloud unit prices (k8s cost model)."),
    service_prefix: str | None = typer.Option(None, help="Keep only services with this prefix."),
    exclude_contains: str | None = typer.Option(None, help="Drop services whose name has this."),
    edge_overrides: Path | None = typer.Option(None, help="YAML of disjunctive groups (v2)."),
    knowledge_base: Path | None = typer.Option(None, help="YAML knowledge base / margins (v2)."),
) -> None:
    """Run the pipeline and print the envelope and any faults."""
    src = get_source(source, topology=topology, metrics_from=metrics_from)  # type: ignore[arg-type]
    target = _build_target(max_latency_ms, min_availability_pct, max_cost_eur_h)
    svc_filter: dict | None = None
    if service_prefix or exclude_contains:
        svc_filter = {}
        if service_prefix:
            svc_filter["include_prefix"] = service_prefix
        if exclude_contains:
            svc_filter["exclude_contains"] = exclude_contains
    edges = yaml.safe_load(edge_overrides.read_text()) if edge_overrides else None
    kb = None
    if knowledge_base is not None:
        from slacheck.models import KnowledgeBase

        kb = KnowledgeBase(**yaml.safe_load(knowledge_base.read_text()))
    price = None
    if pricing is not None:
        from slacheck.models import Pricing

        price = Pricing(**yaml.safe_load(pricing.read_text()))
    result = analyze(
        src, entrypoint, constraint, target=target, sink=sink,  # type: ignore[arg-type]
        paper_version=paper_version, edge_overrides=edges, kb=kb, pricing=price,  # type: ignore[arg-type]
        service_filter=svc_filter,
    )
    _apply_cost_overrides(result, cost_overrides)
    if cost_overrides is not None and paper_version == "v1":
        # re-evaluate now that costs are present (v1 path only)
        from slacheck.envelope.faults import evaluate

        result.verdict = evaluate(result.path, target)
    _render(result)


@app.command()
def publish(
    entrypoint: str = typer.Option(..., "--entrypoint", "-e"),
    constraint: str = typer.Option("latency", "--constraint", "-c"),
    source: str = typer.Option("live", "--source"),
    paper_version: str = typer.Option("v2", "--paper-version", help="v1 | v2"),
    sink: str | None = typer.Option(None, "--sink"),
    min_availability_pct: float | None = typer.Option(None),
    max_latency_ms: float | None = typer.Option(None),
    pricing: Path | None = typer.Option(None, help="YAML cloud unit prices (k8s cost model)."),
    service_prefix: str | None = typer.Option(None, help="Keep only services with this prefix."),
    exclude_contains: str | None = typer.Option(None, help="Drop services whose name has this."),
    title: str | None = typer.Option(None, help="Dashboard title (idempotent key)."),
    dry_run: bool = typer.Option(False, help="Build the JSON but do not push."),
) -> None:
    """Build the verdict dashboard and push it to Datadog."""
    from slacheck.dashboard.builder import build_dashboard

    src = get_source(source)  # type: ignore[arg-type]
    target = _build_target(max_latency_ms, min_availability_pct, None)
    svc_filter: dict | None = None
    if service_prefix or exclude_contains:
        svc_filter = {}
        if service_prefix:
            svc_filter["include_prefix"] = service_prefix
        if exclude_contains:
            svc_filter["exclude_contains"] = exclude_contains
    price = None
    if pricing is not None:
        from slacheck.models import Pricing

        price = Pricing(**yaml.safe_load(pricing.read_text()))
    result = analyze(
        src, entrypoint, constraint, target=target, sink=sink,  # type: ignore[arg-type]
        paper_version=paper_version, pricing=price, service_filter=svc_filter,  # type: ignore[arg-type]
    )
    dashboard = build_dashboard(result, title=title)

    if dry_run:
        typer.echo(json.dumps(dashboard, indent=2))
        return

    from slacheck.dashboard.publisher import publish as do_publish

    url = do_publish(dashboard, Settings())
    typer.secho(f"Published: {url}", fg=typer.colors.GREEN)


@app.command()
def record(
    out: Path = typer.Option(_REPO_ROOT / "fixtures" / "datadog", help="Output fixtures dir."),
) -> None:
    """Capture live Datadog responses into fixtures/. Resilient: records what it can,
    reports which endpoints are denied (so you know exactly which scopes to request)."""
    src = get_source("live")
    out.mkdir(parents=True, exist_ok=True)
    captures = {
        "service_dependencies.json": lambda: src.service_dependencies(),
        "metrics_latency_p99.json": lambda: src.metric_series("latency_p99"),
        "metrics_error_rate.json": lambda: src.metric_series("error_count"),
        "metrics_request_rate.json": lambda: src.metric_series("request_count"),
        "slo_list.json": lambda: src.list_slos(),
    }
    ok, failed = 0, 0
    for name, fetch in captures.items():
        try:
            payload = fetch()
        except Exception as exc:  # noqa: BLE001 — record-what-you-can, report the rest
            failed += 1
            reason = str(exc).splitlines()[0]
            typer.secho(f"SKIP {name}: {type(exc).__name__}: {reason}", fg=typer.colors.YELLOW)
            continue
        (out / name).write_text(json.dumps(payload, indent=2))
        ok += 1
        typer.secho(f"wrote {out / name}", fg=typer.colors.GREEN)

    typer.echo(f"\nCaptured {ok}/{ok + failed} endpoints.")
    if failed:
        typer.secho(
            "Some endpoints were denied — grant the app key the scopes in "
            "docs/datadog_api_catalog.md ('Access checklist') and re-run.",
            fg=typer.colors.YELLOW,
        )


@app.command()
def doctor() -> None:
    """Check that .env credentials + site are accepted by Datadog (no key is printed)."""
    settings = Settings()
    api_state = "set" if settings.api_key else "MISSING"
    app_state = "set" if settings.app_key else "MISSING"
    typer.echo(
        f"site={settings.site}  env={settings.env}  "
        f"api_key={api_state}  app_key={app_state}"
    )

    if not settings.has_credentials:
        typer.secho(
            "Missing DD_API_KEY and/or DD_APP_KEY in .env. "
            "Read endpoints (topology, metrics, dashboards) require BOTH keys.",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=1)

    from slacheck.datadog.live_client import LiveClient

    try:
        ok = LiveClient(settings).validate()
    except Exception as exc:  # noqa: BLE001 — surface the API error to the user
        typer.secho(f"Validation call failed: {exc}", fg=typer.colors.RED)
        typer.secho(
            "If this is a 403, confirm DD_SITE (EU vs US) and the app key scopes.",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(code=1) from exc

    if ok:
        typer.secho("Credentials valid for this site. ✅", fg=typer.colors.GREEN)
    else:
        typer.secho("API key rejected for this site — check DD_SITE.", fg=typer.colors.RED)
        raise typer.Exit(code=1)


@app.command(name="eval")
def eval_cmd(
    dataset: Path = typer.Option(_EVAL_DATASET, help="Eval dataset dir."),
    paper_version: str = typer.Option("v2", "--paper-version", help="v1 | v2"),
    both: bool = typer.Option(False, help="Show v1 and v2 side by side."),
    latex: bool = typer.Option(False, help="Emit a paper-ready LaTeX table (v1 vs v2)."),
) -> None:
    """Reproduce the paper's fault-detection Table I for v1 and/or v2."""
    from slacheck.eval.runner import format_latex, format_table, run_eval

    if not any(dataset.glob("*/*.yaml")):
        typer.secho(
            f"No scenarios under {dataset}. Pass --dataset DIR (one sub-directory per class).",
            fg=typer.colors.RED,
        )
        raise typer.Exit(code=2)

    if latex:
        v1, v2 = run_eval(dataset, "v1"), run_eval(dataset, "v2")
        typer.echo(format_latex(v1, v2))
        return

    versions = ["v1", "v2"] if both else [paper_version]
    for ver in versions:
        report = run_eval(dataset, ver)  # type: ignore[arg-type]
        typer.echo(format_table(report, ver))
        typer.echo("")


@app.command()
def check(
    topology: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="Topology or OpenSLO YAML."
    ),
    slo: float | None = typer.Option(None, "--slo", help="Target availability (%), e.g. 99.9."),
    max_latency_ms: float | None = typer.Option(None, help="Target max end-to-end latency (ms)."),
    max_cost_eur_h: float | None = typer.Option(None, help="Target max cost (EUR/h)."),
    paper_version: str = typer.Option("v2", "--paper-version", help="v1 | v2"),
    both: bool = typer.Option(False, help="Run v1 (baseline) and v2 (full method) in turn."),
    independent: bool = typer.Option(
        False, "--independent", help="Check only availability using independent service states."
    ),
    graph_file: Path | None = typer.Option(
        None, "--graph", exists=True, dir_okay=False, help="Topology YAML for an OpenSLO input."
    ),
    slo_name: str | None = typer.Option(None, help="Select an SLO in an OpenSLO bundle."),
) -> None:
    """Check a declared topology, or an OpenSLO availability target with --graph.

    Command-line targets override targets in the input. Exits 1 when the last check finds a fault.
    """
    from slacheck.envelope.faults import evaluate as evaluate_v1
    from slacheck.envelope.v2.evaluate_v2 import evaluate_v2
    from slacheck.eval.runner import load_scenario

    if slo_name is not None and graph_file is None:
        raise typer.BadParameter("--slo-name requires OpenSLO YAML with --graph.")
    try:
        sc = load_scenario(graph_file or topology)
        graph = sc["graph"]
        target = sc["target"]
        if graph_file is not None:
            goal = load_openslo_target(topology, slo_name)
            if graph.entrypoint != goal.service:
                raise ValueError(f"set the topology entrypoint to {goal.service!r} (spec.service).")
            target = (target or SloValues()).model_copy(
                update={"availability_pct": goal.availability_pct}
            )
    except (OSError, ValueError, TypeError, KeyError, yaml.YAMLError) as exc:
        raise typer.BadParameter(
            f"Could not load check input: {exc}. See examples/shop.yaml for the topology format."
        ) from exc
    overrides = {
        "availability_pct": slo,
        "response_time_ms": max_latency_ms,
        "cost_eur_h": max_cost_eur_h,
    }
    overrides = {k: v for k, v in overrides.items() if v is not None}
    if overrides:
        target = (target or SloValues()).model_copy(update=overrides)

    if independent:
        other_metrics = max_latency_ms is not None or max_cost_eur_h is not None
        if both or paper_version != "v2" or other_metrics:
            raise typer.BadParameter("--independent checks availability only; use it with --slo.")
        if target is None or target.availability_pct is None:
            raise typer.BadParameter("Pass --slo or set global_target.availability_pct.")
        try:
            result = check_availability(graph, target.availability_pct)
        except ValueError as exc:
            raise typer.BadParameter(str(exc)) from exc
        typer.echo("Model: independent service states; declared availabilities without margins.")
        typer.echo(f"Target: {result.target_pct:.12g}%")
        typer.echo(f"Achievable: {result.achievable_pct:.12g}%")
        typer.echo("Minimum availability with all other services unchanged:")
        for name, threshold in result.thresholds_pct.items():
            value = (
                "not repairable by this service alone"
                if threshold is None
                else f"{threshold:.12g}%"
            )
            typer.echo(f"  {name}: {value}")
        typer.echo("Feasible" if result.feasible else "Infeasible")
        if not result.feasible:
            raise typer.Exit(code=1)
        return

    if target is not None:
        typer.echo(f"Target Global-SLO : {target.model_dump(exclude_none=True)}")

    verdict = None
    for ver in ["v1", "v2"] if both else [paper_version]:
        if ver == "v1":
            path = [graph.components[n] for n in graph.topological_order()]
            verdict = evaluate_v1(path, target)
            if sc["strategies"]:
                verdict.notes.append(
                    f"v1 has no reconfiguration model: {len(sc['strategies'])} elasticity "
                    "strategy(ies) in this file were not checked."
                )
        else:
            verdict = evaluate_v2(
                graph, target, sc["kb"], sc["strategies"], sc["target_slos"]
            )
            path = [graph.components[n] for n in verdict.envelope.path]
        typer.secho(f"\n=== {ver} ===", bold=True)
        _render(
            AnalysisResult(
                entrypoint=graph.entrypoint,
                constraint="availability",
                path=path,
                verdict=verdict,
                dropped_edges=[],
                paper_version=ver,  # type: ignore[arg-type]
            )
        )
    if verdict is not None and verdict.faults:
        raise typer.Exit(code=1)


@app.command("import-trace")
def import_trace(
    export: Path = typer.Argument(..., exists=True, dir_okay=False, help="Saved trace or metrics."),
    source: TraceSource = typer.Option(..., "--source", help="Export format."),
    entrypoint: str | None = typer.Option(None, help="Root service of the commitment scope."),
) -> None:
    """Write a topology YAML from OTLP, Jaeger, or Tempo service graph data."""
    try:
        graph = load_trace_graph(export, source, entrypoint)
    except (OSError, ValueError) as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(yaml.safe_dump({
        "entrypoint": graph.entrypoint,
        "components": [
            {"name": service, "slo": {"availability_pct": None}} for service in graph.components
        ],
        "edges": [edge.model_dump() for edge in graph.edges],
    }, sort_keys=False), nl=False)


@app.command()
def catalog() -> None:
    """Where to read what Datadog exposes for slacheck."""
    typer.echo("See docs/datadog_api_catalog.md — endpoints, metric→SLO conversions, and gaps.")


if __name__ == "__main__":
    app()
