#!/bin/bash
# Verify APM tracing across train-ticket services: which deployments carry the dd-java-agent patch,
# and which are actually emitting servlet.request spans in Datadog over the last window.
#
# Usage:  scripts/loadgen/check_tracing.sh          # needs .env with DD_* for the live check
set -u
NS="${NAMESPACE:-tt-slacheck}"
SKIP_RE='mongo|mysql|redis|rabbitmq|nacos|zipkin|jaeger|ui-dashboard'
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
[ -f "$REPO/.env" ] && { set -a; . "$REPO/.env"; set +a; }
SITE="${DD_SITE:-datadoghq.com}"

SERVICES=$(kubectl get deploy -n "$NS" -o name 2>/dev/null | sed 's|deployment.apps/||' \
  | grep '^ts-' | grep -vE "$SKIP_RE" | sort)

patched=0; unpatched=0; up=""
for svc in $SERVICES; do
  jto=$(kubectl get deploy -n "$NS" "$svc" \
    -o jsonpath='{range .spec.template.spec.containers[0].env[*]}{.name}={.value}{"\n"}{end}' 2>/dev/null \
    | grep JAVA_TOOL_OPTIONS)
  if echo "$jto" | grep -q "dd-java-agent"; then patched=$((patched+1));
  else unpatched=$((unpatched+1)); up="$up $svc"; fi
done
echo "== deployment patch state: $patched patched, $unpatched not patched =="
[ -n "$up" ] && echo "   not patched:$up"

# live: how many distinct services emit servlet.request hits in the last 15 min
if [ -n "${DD_API_KEY:-}" ] && [ -n "${DD_APP_KEY:-}" ]; then
  NOW=$(date +%s); FROM=$((NOW-900))
  echo ""
  echo "== live servlet.request.hits over last 15 min (services actually tracing) =="
  curl -s --max-time 20 -G "https://api.${SITE}/api/v1/query" \
    -H "DD-API-KEY: $DD_API_KEY" -H "DD-APPLICATION-KEY: $DD_APP_KEY" \
    --data-urlencode "from=$FROM" --data-urlencode "to=$NOW" \
    --data-urlencode "query=sum:trace.servlet.request.hits{service:ts-*} by {service}.as_count()" \
  | python3 -c "
import sys,json
d=json.load(sys.stdin)
s=d.get('series',[])
live=[x.get('scope','?').replace('service:','') for x in s if sum(p[1] for p in x.get('pointlist',[]) if p[1])>0]
print(f'  {len(live)} services with live spans:')
for n in sorted(live): print('   ',n)
"
fi
