# Changelog

## 0.2.0

- Add `slacheck check --independent` for availability with shared dependencies,
  exact conditional service thresholds, and ranked single-service repairs.
- Accept OpenSLO v1 request availability targets with a declared topology.
- Import a dependency graph from OTLP JSON, Jaeger JSON, or Tempo service graph metrics.
- Add JSON and SARIF check reports and a composite GitHub Action.
- Add `make bench` with an exhaustive oracle and pinned reference tool releases.
- Keep paper v2 as the default: the independent model assumes independent states
  for distinct services and does not apply paper safety margins. Select it
  explicitly, or continue to use `--paper-version v1|v2`.

## 0.1.0

- Paper v1 and v2 analyses, a declared-topology CLI, offline fixture evaluation,
  and a Datadog integration.
