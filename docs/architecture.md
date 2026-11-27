# Architecture

## Separate objective, topology and measurements

OpenSLO describes the request objective and service. Trace imports describe
observed caller and callee pairs. Neither source provides a complete set of
local availability measurements or proves that a dependency is redundant.
The declared topology joins these inputs. Imports leave availabilities blank,
mark edges required and reject cycles in the selected scope.

## Evaluate one state per service

The independent checker models each service as a Boolean up/down variable. A
call succeeds if its service is up, every required callee succeeds, and at least
one callee in its alternative group succeeds. A shared dependency is one
variable even when it has several callers.

A reduced ordered decision diagram represents that success condition. Bottom-up
evaluation computes failure probabilities. A reverse traversal accumulates how
much each service changes the failure probability. The result is affine in one
service's availability with the others fixed, so the checker can solve the
threshold directly rather than searching candidate values.

Large or densely overlapping topologies may be expensive to compile. The checker
rejects scopes that exceed its size or depth limit. A synthetic exhaustive oracle
checks small graphs in `make bench`; runtime measurements use two 200-service
graphs. Arbitrary correlation between distinct services is not inferred.

## Preserve paper evaluations

Paper v1 and v2 remain available for reproducing earlier evaluations. Paper v2
estimates safety margins and includes latency, costs, and reconfiguration checks.
Its structural weights allocate a budget, which is a different question from
the minimum required by one service with other values fixed. The CLI keeps v2
as its default instead of silently changing the model.
