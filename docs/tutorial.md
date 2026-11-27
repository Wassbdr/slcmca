# Check your own service graph

## Define the commitment scope

Choose one request path, an entrypoint service, a measurement window, and the
availability commitment for that scope. Measure each service's own probability
of a successful request, excluding failures already counted in its dependencies.
Use the same window and request population for all inputs.

Start from [the shop topology](https://github.com/Wassbdr/slcmca/blob/showcase/2026-11/examples/shop.yaml)
or import a graph from a file:

```sh
slacheck import-trace otlp.json --source otlp --entrypoint frontend > topology.yaml
slacheck import-trace jaeger.json --source jaeger --entrypoint frontend > topology.yaml
slacheck import-trace service-graph.prom --source tempo --entrypoint frontend > topology.yaml
```

Choose one import command. For Tempo, export `traces_service_graph_request_total`
with `client` and `server` labels as Prometheus text or a JSON vector/matrix
response. A missing observed edge is not evidence that a dependency is optional.

Fill each `slo.availability_pct` and verify the caller-to-callee edges. Every
`conjunctive` dependency is required. A caller's `disjunctive` edges form one
group of alternatives; at least one must be available. Include shared failure
domains as dependencies if you can measure their probabilities separately.

## Check and act on the result

```sh
slacheck check topology.yaml --independent --slo 99.9
slacheck check topology.yaml --independent --slo 99.9 --format json
```

Exit 0 means feasible under the selected model, 1 means infeasible, and 2 means
the input needs correction. Thresholds hold other services unchanged. A null
threshold means fixing this service alone cannot meet the objective. By default
repairs are ranked by the increase in availability, not by engineering spend.
Supply `--improvement-costs costs.yaml` with a mapping from service name to cost
per percentage point to rank by estimated spend.

For CI, copy the
[example workflow](https://github.com/Wassbdr/slcmca/blob/showcase/2026-11/examples/workflows/availability.yml)
to `.github/workflows/` and set the input paths. The action fails the job for an
infeasible target. Uploading SARIF needs code scanning and a token with
`security-events: write`; set `upload-sarif: "false"` when upload is unavailable.
