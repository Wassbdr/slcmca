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

| Method | Execution | Development median / max | Held-out median / max |
| --- | --- | ---: | ---: |
| slacheck independent | In process | 2.36 / 3.01 | 1.53 / 9.07 |
| slacheck v2 | In process | 9.13 / 9.40 | 13.23 / 14.11 |
| Hand error budget | In process | 1.65 / 1.78 | 2.08 / 2.27 |
| slacheck independent CLI | CLI | 141.32 / 281.72 | 141.00 / 282.17 |
| Sloth | CLI | 22.82 / 24.19 | 23.36 / 25.52 |
| Pyrra | CLI | 14.11 / 14.53 | 14.26 / 16.28 |
| OpenSLO | CLI | 4.31 / 5.15 | 4.27 / 4.99 |

## Iteration 1: model shared service states and solve conditional thresholds

V2 counted shared required services along each path, and treated fallback branches
with a shared dependency as independent. Its service thresholds were budget
allocations, not the minimum availability with other services held fixed.

| Metric | Baseline v2 | Decision diagram | Delta |
| --- | ---: | ---: | ---: |
| Infeasible commitments found | 29/34 | 34/34 | +5 |
| False positives | 8 | 0 | -8 |
| Exact conditional thresholds | 0/712 | 712/712 | +712 |
