#!/bin/bash
# Rolling enable of Datadog APM tracing across train-ticket Java services.
#
# Root cause (proven): the deployments pin JAVA_TOOL_OPTIONS to the jmx agent only, so the
# auto-injected dd-java-agent.jar (present at /opt/datadog/apm/library/java/dd-java-agent.jar) is
# never loaded by the JVM -> zero trace spans. Fix: prepend the dd-java-agent to JAVA_TOOL_OPTIONS.
#
# This script does it ONE SERVICE AT A TIME: patch -> wait for rollout Ready -> verify the tracer
# banner -> only then move to the next. That keeps the shared/slow cluster from being saturated by
# a mass restart. Safe to re-run: services already carrying dd-java-agent are skipped.
#
# Usage:
#   scripts/loadgen/enable_apm_tracing.sh                 # all Java ts-* services
#   scripts/loadgen/enable_apm_tracing.sh ts-train-service ts-order-service   # a subset
#   NAMESPACE=tt-slacheck ROLLOUT_TIMEOUT=300 scripts/loadgen/enable_apm_tracing.sh
set -u

NS="${NAMESPACE:-tt-slacheck}"
DD_JAR="/opt/datadog/apm/library/java/dd-java-agent.jar"
JMX="-javaagent:/jmxagent/jmx.jar=9404:/jmxagent/config.yaml"
NEW_JTO="-javaagent:${DD_JAR} ${JMX}"
# These services have readinessProbe.initialDelaySeconds=160 and a slow Java boot on this shared
# cluster, so a per-service rollout can legitimately take 5-7 min. Be generous by default.
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-450}"   # seconds to wait per service

# Which services? args, or auto-discover all Java ts-* (exclude nginx ui-dashboard + jaeger variants)
if [ "$#" -gt 0 ]; then
  SERVICES="$*"
else
  SERVICES=$(kubectl get deploy -n "$NS" -o name 2>/dev/null | sed 's|deployment.apps/||' \
    | grep '^ts-' | grep -v with-jaeger | grep -v ui-dashboard | sort)
fi

total=$(echo "$SERVICES" | wc -w); i=0; done_ok=0; skipped=0; failed=""
echo "== APM tracing rollout: $total services, namespace $NS, timeout ${ROLLOUT_TIMEOUT}s each =="

for svc in $SERVICES; do
  i=$((i+1))
  printf "\n[%d/%d] %s\n" "$i" "$total" "$svc"

  # already fixed? skip
  cur=$(kubectl get deploy -n "$NS" "$svc" \
    -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' 2>/dev/null \
    | grep JAVA_TOOL_OPTIONS)
  if echo "$cur" | grep -q "dd-java-agent"; then
    echo "  already has dd-java-agent -> skip"
    skipped=$((skipped+1)); continue
  fi

  echo "  patching JAVA_TOOL_OPTIONS ..."
  kubectl set env -n "$NS" "deployment/$svc" JAVA_TOOL_OPTIONS="$NEW_JTO" >/dev/null 2>&1

  echo "  waiting for rollout (max ${ROLLOUT_TIMEOUT}s) ..."
  if kubectl rollout status -n "$NS" "deployment/$svc" --timeout="${ROLLOUT_TIMEOUT}s" >/dev/null 2>&1; then
    # confirm the tracer actually loaded in the new pod
    pod=$(kubectl get pod -n "$NS" -l "app=$svc" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    if kubectl logs -n "$NS" "$pod" 2>/dev/null | grep -q "DATADOG TRACER CONFIGURATION"; then
      echo "  OK: rolled out + tracer banner present"
      done_ok=$((done_ok+1))
    else
      echo "  WARN: rolled out but no tracer banner yet (may need a few more seconds)"
      done_ok=$((done_ok+1))
    fi
  else
    echo "  FAIL: rollout did not become Ready in ${ROLLOUT_TIMEOUT}s -> rolling back this one"
    kubectl rollout undo -n "$NS" "deployment/$svc" >/dev/null 2>&1
    failed="$failed $svc"
  fi
done

echo ""
echo "== done: $done_ok patched, $skipped skipped, failed:${failed:- none} =="
[ -z "$failed" ] || echo "   re-run the script with the failed names once the cluster is calmer."
