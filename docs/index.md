# slacheck

Check whether a distributed application can meet its availability objective
before committing to it. Start with the [tutorial](tutorial.md), then use a
[worked example](examples.md) to try an OpenSLO objective, imported traces, or
a priced repair.

```sh
python -m pip install .
slacheck check examples/shop.yaml --independent --slo 99.94
```

The second command deliberately exits with status 1 and prints repair options.
Use `make docs` after installing `.[docs]` to build this site locally.
