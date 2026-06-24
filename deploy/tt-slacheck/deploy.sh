#!/usr/bin/env bash
# Deploy a SECOND train-ticket into namespace `tt-slacheck` with Datadog APM auto-injection,
# so slacheck has its own Datadog-traced instance. Does NOT touch `tt` / `tt-b` (RCA work).
#
# Prereqs (verified on observit-cluster1):
#   - kube context = observit-cluster1
#   - Datadog Cluster Agent admission controller + APM auto-instrumentation enabled
#   - helm 3.x
set -euo pipefail

NS=tt-slacheck
CHARTS=/home/wassimbadraoui/repos/train-ticket/deployment/kubernetes-manifests/quickstart-k8s/charts
HERE="$(cd "$(dirname "$0")" && pwd)"

echo ">> context: $(kubectl config current-context)"

kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -

# Infra deps via the bundled charts.
# IMPORTANT: the nacos chart hardcodes its DB host as `nacos-mysql-leader`, so the MySQL
# chart MUST be installed with fullnameOverride=nacos-mysql (NOT release name `mysql`),
# else nacos's initmysql container CrashLoops on "Unknown MySQL host 'nacos-mysql-leader'".
helm upgrade --install nacos-mysql "$CHARTS/mysql" -n "$NS" --set fullnameOverride=nacos-mysql --timeout 10m
helm upgrade --install nacos       "$CHARTS/nacos" -n "$NS" --timeout 10m
helm upgrade --install rabbitmq    "$CHARTS/rabbitmq" -n "$NS" --timeout 10m

# Wait for nacos (the config registry every ts-* service depends on) to be ready.
echo ">> waiting for nacos-0 to become Ready..."
kubectl wait --for=condition=ready pod/nacos-0 -n "$NS" --timeout=10m || true

# Secrets + services + the Datadog-patched deployments.
kubectl apply -n "$NS" -f "$HERE/secret.yaml"
kubectl apply -n "$NS" -f "$HERE/svc.yaml"
kubectl apply -n "$NS" -f "$HERE/deploy.datadog.yaml"

cat <<'EOF'
>> rollout started. Watch:   kubectl get pods -n tt-slacheck -w
>> Datadog injects dd-java-agent at pod creation; traces appear under env:slacheck.
>> train-ticket has NO traffic by itself — the service map only draws edges from real calls.
>>   Drive load (e.g. via the train-ticket-auto-query repo, or port-forward ts-ui-dashboard and click),
>>   then check Datadog APM -> Service Catalog (filter env:slacheck).
EOF
