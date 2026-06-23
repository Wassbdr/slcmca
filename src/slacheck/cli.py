"""slacheck CLI (typer). Offline-first: --source fixture is the default.

Commands:
  analyze   run the pipeline and print envelope + faults (fixture or live)
  publish   build the dashboard and push it to Datadog (live, needs dashboards_write)
  record    capture live API responses into fixtures/datadog/ (live, needs keys)
  catalog   point to the Datadog API catalog doc
"""

from __future__ import annotations

import json
from pathlib import Path

import typer
import yaml

from slacheck.config import Settings
from slacheck.datadog.source import get_source
from slacheck.models import SloValues
from slacheck.pipeline import AnalysisResult, analyze

app = typer.Typer(add_completion=False, help="Achievable SLA envelope from Datadog topology.")

_REPO_ROOT = Path(__file__).resolve().parents[2]


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
    typer.echo(f"Critical path : {' -> '.join(env.path)}")
    typer.echo("\nAchievable envelope:")
    typer.echo(f"  latency      : {env.response_time_ms!r} ms")
    typer.echo(f"  availability : {env.availability_pct!r} %")
    typer.echo(f"  cost         : {env.cost_eur_h!r} EUR/h")

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
    source: str = typer.Option("fixture", "--source", help="fixture | live"),
    sink: str | None = typer.Option(None, "--sink", help="Optional target/sink service."),
    max_latency_ms: float | None = typer.Option(None, help="Global target: max latency (ms)."),
    min_availability_pct: float | None = typer.Option(None, help="Global target: min avail (%)."),
    max_cost_eur_h: float | None = typer.Option(None, help="Global target: max cost (EUR/h)."),
    cost_overrides: Path | None = typer.Option(None, help="YAML of per-service EUR/h."),
) -> None:
    """Run the pipeline and print the envelope and any faults."""
    src = get_source(source)  # type: ignore[arg-type]
    target = _build_target(max_latency_ms, min_availability_pct, max_cost_eur_h)
    result = analyze(src, entrypoint, constraint, target=target, sink=sink)  # type: ignore[arg-type]
    _apply_cost_overrides(result, cost_overrides)
    if cost_overrides is not None:
        # re-evaluate now that costs are present
        from slacheck.envelope.faults import evaluate

        result.verdict = evaluate(result.path, target)
    _render(result)


@app.command()
def publish(
    entrypoint: str = typer.Option(..., "--entrypoint", "-e"),
    constraint: str = typer.Option("latency", "--constraint", "-c"),
    source: str = typer.Option("live", "--source"),
    sink: str | None = typer.Option(None, "--sink"),
    min_availability_pct: float | None = typer.Option(None),
    max_latency_ms: float | None = typer.Option(None),
    title: str | None = typer.Option(None, help="Dashboard title (idempotent key)."),
    dry_run: bool = typer.Option(False, help="Build the JSON but do not push."),
) -> None:
    """Build the verdict dashboard and push it to Datadog."""
    from slacheck.dashboard.builder import build_dashboard

    src = get_source(source)  # type: ignore[arg-type]
    target = _build_target(max_latency_ms, min_availability_pct, None)
    result = analyze(src, entrypoint, constraint, target=target, sink=sink)  # type: ignore[arg-type]
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
    """Capture live Datadog responses into fixtures/datadog/ (needs keys)."""
    src = get_source("live")
    out.mkdir(parents=True, exist_ok=True)
    captures = {
        "service_dependencies.json": src.service_dependencies(),
        "metrics_latency_p99.json": src.metric_series("latency_p99"),
        "metrics_error_rate.json": src.metric_series("error_count"),
        "metrics_request_rate.json": src.metric_series("request_count"),
        "slo_list.json": src.list_slos(),
    }
    for name, payload in captures.items():
        (out / name).write_text(json.dumps(payload, indent=2))
        typer.echo(f"wrote {out / name}")


@app.command()
def catalog() -> None:
    """Where to read what Datadog exposes for slacheck."""
    typer.echo("See docs/datadog_api_catalog.md — endpoints, metric→SLO conversions, and gaps.")


if __name__ == "__main__":
    app()
