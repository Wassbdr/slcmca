# Changelog

## 0.2.0

- Make exact availability the default for `slacheck check`, with shared
  dependencies, conditional service thresholds, and ranked single-service repairs.
- Accept OpenSLO v1 request availability targets with a declared topology.
- Import a dependency graph from OTLP JSON, Jaeger JSON, or Tempo service graph metrics.
- Add JSON and SARIF check reports and a composite GitHub Action.
- Add `make bench` with an exhaustive oracle and pinned reference tool releases.
- Use `--method v2` for paper safety margins, latency, cost, and reconfiguration
  checks. The exact checker assumes independent states for distinct services.
  `--independent` is a deprecated alias for `--method exact`, and
  `--paper-version v1|v2` remains an alias for the paper methods.

## 0.1.0

- Paper v1 and v2 analyses, a declared-topology CLI, offline fixture evaluation,
  and a Datadog integration.
