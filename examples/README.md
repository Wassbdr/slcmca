# Example inputs

`hotrod.otlp.json` is a synthetic OTLP trace based on the public
[Jaeger HotROD topology](https://github.com/jaegertracing/jaeger/tree/main/examples/hotrod).
The upstream app is [Apache-2.0 licensed](https://github.com/jaegertracing/jaeger/blob/main/LICENSE).
No trace capture, request payload, or user data was copied. Regenerate it with
`python scripts/make_hotrod_sample.py`.

```sh
slacheck import-trace examples/hotrod.otlp.json --source otlp > hotrod.yaml
```

Fill in each service's `slo.availability_pct` before checking the topology.
Observed edges are required by default; explicitly mark alternatives as
`disjunctive` when any one can satisfy the caller.
