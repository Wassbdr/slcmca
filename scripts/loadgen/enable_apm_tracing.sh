#!/bin/bash
# Rolling enable of Datadog APM tracing across train-ticket Java services.
#
# Root cause (proven): the deployments pin JAVA_TOOL_OPTIONS to the jmx agent only, so the
# auto-injected dd-java-agent.jar (present at /opt/datadog/apm/library/java/dd-java-agent.jar) is
# never loaded by the JVM -> zero trace spans. Fix: prepend the dd-java-agent to JAVA_TOOL_OPTIONS.
#
# Strategy (learned the hard way): these Spring services have readinessProbe.initialDelaySeconds=160
# and a slow Java boot on this shared cluster, so waiting for full readiness per service costs
# 6-10 min EACH and `kubectl rollout status` often declares a false FAIL just before the pod turns
# Ready. So we DO NOT block on readiness and DO NOT roll back: we apply the patch (idempotent, safe)
# and move on after a short pacing delay so we never restart too many pods at once. The patch is what
# matters; the pod becomes Ready on its own schedule. Datastores (mongo/redis/rabbitmq) are skipped —
# they run no servlet, so tracing them is pointless and they use different readiness ports.
#
# Verify afterwards with:  scripts/loadgen/check_tracing.sh   (or query trace.servlet.request.hits)
#
# Usage:
#   scripts/loadgen/enable_apm_tracing.sh                 # all Java ts-* services
#   scripts/loadgen/enable_apm_tracing.sh ts-train-service ts-order-service   # a subset
#   PACE=25 NAMESPACE=tt-slacheck scripts/loadgen/enable_apm_tracing.sh
set -u

NS="${NAMESPACE:-tt-slacheck}"
DD_JAR="/opt/datadog/apm/library/java/dd-java-agent.jar"
JMX="-javaagent:/jmxagent/jmx.jar=9404:/jmxagent/config.yaml"
NEW_JTO="-javaagent:${DD_JAR} ${JMX}"
PACE="${PACE:-25}"          # seconds between patches — throttle so restarts don't pile up
MAX_INFLIGHT="${MAX_INFLIGHT:-6}"   # pause if more than this many ts-* pods are NotReady

# Datastores and infra that run no servlet — skip (no traces to gain, different readiness ports).
SKIP_RE='mongo|mysql|redis|rabbitmq|nacos|zipkin|jaeger|ui-dashboard'

if [ "$#" -gt 0 ]; then
  SERVICES="$*"
else
  SERVICES=$(kubectl get deploy -n "$NS" -o name 2>/dev/null | sed 's|deployment.apps/||' \
    | grep '^ts-' | grep -vE "$SKIP_RE" | sort)
fi

notready_count() {
  kubectl get pods -n "$NS" --no-headers 2>/dev/null | grep -E "^ts-" \
    | awk '{split($2,a,"/"); if(a[1]!=a[2]) n++} END{print n+0}'
}

total=$(echo "$SERVICES" | wc -w); i=0; patched=0; skipped=0
echo "== APM tracing rollout: $total Java services, ns $NS, pace ${PACE}s, no-rollback mode =="

for svc in $SERVICES; do
  i=$((i+1))
  printf "\n[%d/%d] %s\n" "$i" "$total" "$svc"

  cur=$(kubectl get deploy -n "$NS" "$svc" \
    -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' 2>/dev/null \
    | grep JAVA_TOOL_OPTIONS)
  if echo "$cur" | grep -q "dd-java-agent"; then
    echo "  already patched -> skip"; skipped=$((skipped+1)); continue
  fi

  # backpressure: don't let too many pods restart at once
  while [ "$(notready_count)" -gt "$MAX_INFLIGHT" ]; do
    echo "  $(notready_count) pods NotReady (> $MAX_INFLIGHT) — pausing 30s for the cluster to catch up"
    sleep 30
  done

  echo "  patching JAVA_TOOL_OPTIONS (dd-java-agent + jmx) ..."
  if kubectl set env -n "$NS" "deployment/$svc" JAVA_TOOL_OPTIONS="$NEW_JTO" >/dev/null 2>&1; then
    echo "  PATCHED (pod will restart and become Ready on its own; not blocking)"
    patched=$((patched+1))
  else
    echo "  ERROR: kubectl set env failed for $svc"
  fi
  sleep "$PACE"
done

echo ""
echo "== done: $patched patched, $skipped skipped =="
echo "   pods will finish rolling over the next several minutes; verify with check_tracing.sh"
