# Availability benchmark

From an environment with `python -m pip install -e .`, put these release binaries on PATH:

| Tool | Linux x86-64 release |
| --- | --- |
| Sloth 0.11.0 | [sloth-linux-amd64](https://github.com/slok/sloth/releases/download/v0.11.0/sloth-linux-amd64) |
| Pyrra 0.8.4 | [Linux archive](https://github.com/prometheus-community/pyrra/releases/download/v0.8.4/pyrra_0.8.4_Linux_x86_64.tar.gz) |
| OpenSLO oslo 0.13.0 | [oslo-0.13.0-linux-amd64](https://github.com/OpenSLO/oslo/releases/download/v0.13.0/oslo-0.13.0-linux-amd64) |

Name the executables `sloth`, `pyrra`, and `oslo`. Run `make bench`. No
Prometheus server is needed. The command writes [results.md](results.md).

- Development: the repository's Alibaba-inspired tree-like generator with
  occasional shared callees, seeds 11, 29 and 47.
- Held out: entrypoint with required stages, each using two interchangeable
  providers that depend on a shared service, seeds 101, 131 and 167.
- Twelve graphs per seed with 6 to 12 services. Inputs are synthetic; component
  unavailability is uniform from 0.01 to 0.8 percentage points. The commitment
  budget is drawn independently of these service availabilities. The first seed
  of each family also generates one 200-service graph for timing.
- The oracle enumerates every up/down assignment for small graphs and evaluates
  the topology as a Boolean success condition. For each service it also sums
  the probabilities of failure with the service forced up or down, then solves
  for the minimum service availability between these endpoints.

Reference commands: `sloth validate`, `pyrra generate`, and `oslo validate`.
Each receives the 30-day entrypoint objective and a synthetic request SLI
selector in its native format. They do not receive the graph because the
tested manifests cannot express dependency success conditions. The benchmark
checks that each command succeeds, including that Pyrra writes its rules.
Acceptance is not a feasibility verdict; the score counts no infeasibility
flags and no service thresholds. We do not compare monitoring or alerting.

The hand worksheet starts with the
[Google SRE Workbook error budget](https://sre.google/workbook/implementing-slos/):
allowed failed requests = (1 - goal) × total requests. It sums the failure
allowance for mandatory services once each (over the same request population).
A service reached by every redundant branch is mandatory and counted once.
This common conservative arithmetic for a required chain is not an exact
probability calculation and ignores residual failure in optional branches.
The Workbook explicitly cautions against ignoring common failure domains;
it does not prescribe this worksheet as a general graph solver.

Use `slacheck check examples/shop.yaml --independent --slo 99.9` for the same
model on a declared topology. It operates on the declared availabilities
without paper-v2 safety margins. Distinct services with correlated failures
need a modeled shared dependency; the probabilities alone do not determine
their correlation. The graph is compiled to a reduced ordered decision
diagram, then one forward and one reverse pass solve the thresholds. Some
graphs require exponentially many decision nodes. The checker refuses scopes
too large to compile instead of substituting an approximation.
