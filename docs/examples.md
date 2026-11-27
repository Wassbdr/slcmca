# Worked examples

Run these commands from the checkout after `python -m pip install .`.

## 1. Catch an infeasible shop commitment

```sh
slacheck check examples/shop.yaml --independent --slo 99.94
```

The target exceeds the modeled envelope. The command exits with status 1 and
prints the ranked service improvements that could close the gap individually.
Edit the named service's `slo.availability_pct` to at least the suggested
threshold, rounding up, and rerun the check.

## 2. Keep the objective in OpenSLO

```sh
slacheck check examples/shop-openslo.yaml --graph examples/shop.yaml --independent --format sarif
```

The OpenSLO bundle supplies a request availability objective for `frontend` and
the graph supplies the local availability estimates. It exits with status 0:
the objective is feasible under the independent model, so SARIF has no findings.
If a bundle contains several SLOs, pick one with `--slo-name`.

## 3. Start with a trace export

```sh
slacheck import-trace examples/hotrod.otlp.json --source otlp > hotrod.yaml
```

The synthetic trace uses the public Jaeger HotROD service layout. The output
includes frontend, customer, driver, route, MySQL, and Redis. Fill in each
availability before running `slacheck check hotrod.yaml --independent --slo 99.9`.
For a rehearsal, assign 99.99% to each service. The six required services meet
99.9% in that scenario. Use measured figures, not those example values, in CI.
