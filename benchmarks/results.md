# Availability commitment benchmark

CPU: Intel(R) Xeon(R) Processor (x86_64); Python 3.10.12; no GPU.
Synthetic per-service probabilities; seeds and reference setup: [README](README.md).
Service states are independent; shared dependencies reuse the same service state.
Single-service thresholds hold all other measurements fixed. A threshold can be
impossible even at 100%. Match tolerance: 0.00000001 percentage points.
Classification uses global commitment faults only, not v2 budget allocation faults.

## Development

36 graphs, 15 infeasible.

| Method | Recall | Precision | False positives | Thresholds matched |
| --- | ---: | ---: | ---: | ---: |
| slacheck independent | 15/15 | 15/15 | 0 | 369/369 |
| slacheck v2 | 15/15 | 15/23 | 8 | 0/369 |
| Hand error budget | 15/15 | 15/19 | 4 | not computed |
| Sloth | 0/15 | n/a | 0 | not computed |
| Pyrra | 0/15 | n/a | 0 | not computed |
| OpenSLO | 0/15 | n/a | 0 | not computed |


## Held-out

36 graphs, 19 infeasible.

| Method | Recall | Precision | False positives | Thresholds matched |
| --- | ---: | ---: | ---: | ---: |
| slacheck independent | 19/19 | 19/19 | 0 | 343/343 |
| slacheck v2 | 14/19 | 14/14 | 0 | 0/343 |
| Hand error budget | 19/19 | 19/19 | 0 | not computed |
| Sloth | 0/19 | n/a | 0 | not computed |
| Pyrra | 0/19 | n/a | 0 | not computed |
| OpenSLO | 0/19 | n/a | 0 | not computed |

slacheck v2 missed: held-out-101-05, held-out-131-01, held-out-131-05, held-out-167-00, held-out-167-08.

## Runtime

Milliseconds for 200 services, seven serial samples per graph. Python methods run
in process on parsed inputs. CLI timings include process start and YAML reading,
plus threshold output for slacheck or validation or rule generation for references.
Reference manifests carry the same root objective and an SLI selector,
not the graph or service availabilities.

| Method | Development median / max | Held-out median / max |
| --- | ---: | ---: |
| slacheck independent | 2.10 / 2.26 | 4.04 / 11.33 |
| slacheck v2 | 9.32 / 10.76 | 13.93 / 18.41 |
| Hand error budget | 1.97 / 3.39 | 2.60 / 3.00 |
| slacheck independent CLI | 326.29 / 356.00 | 342.34 / 351.08 |
| Sloth | 22.75 / 25.21 | 23.74 / 28.15 |
| Pyrra | 14.27 / 16.41 | 14.34 / 17.95 |
| OpenSLO | 4.22 / 4.40 | 4.32 / 4.75 |

## Iteration 1: model shared service states and solve conditional thresholds

V2 counted shared required services along each path, and treated fallback branches
with a shared dependency as independent. Its service thresholds were budget
allocations, not the minimum availability with other services held fixed.

| Metric | Baseline v2 | Decision diagram | Delta |
| --- | ---: | ---: | ---: |
| Infeasible commitments found | 29/34 | 34/34 | +5 |
| False positives | 8 | 0 | -8 |
| Exact conditional thresholds | 0/712 | 712/712 | +712 |
