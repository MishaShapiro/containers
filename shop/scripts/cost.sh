#!/usr/bin/env bash
# usage: cost.sh TESTID — итог k6 и потребление api (и linkerd) за последние 3 минуты этого прогона
set -e
T=${1:?укажи testid, например baseline}
END=$(date -d "$(kubectl get job -n loadtest k6-$T -o jsonpath='{.status.completionTime}')" +%s)
prom() {
  kubectl get --raw "/api/v1/namespaces/monitoring/services/kps-prometheus:9090/proxy/api/v1/query?query=$(
    python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))' "$1")" |
  python3 -c 'import json,sys
for r in json.load(sys.stdin)["data"]["result"]:
    print("   %-16s %8.1f" % (r["metric"].get("container", "всего"), float(r["value"][1])))'
}
echo "== k6 ($T), закончился $(date -d @$END '+%F %T UTC')"
kubectl logs -n loadtest job/k6-$T | grep -E 'http_req_duration|http_req_failed|http_reqs'
echo "== CPU api, millicores (окно 3m до конца теста)"
prom "sum by (container) (rate(container_cpu_usage_seconds_total{namespace=\"shop\",pod=~\"api-v1-.*\",container!=\"\"}[3m] @ $END)) * 1000"
prom "sum(rate(container_cpu_usage_seconds_total{namespace=\"shop\",pod=~\"api-v1-.*\",container!=\"\"}[3m] @ $END)) * 1000"
echo "== RAM api, MiB (среднее за 3m)"
prom "sum by (container) (avg_over_time(container_memory_working_set_bytes{namespace=\"shop\",pod=~\"api-v1-.*\",container!=\"\"}[3m] @ $END)) / 2^20"
prom "sum(avg_over_time(container_memory_working_set_bytes{namespace=\"shop\",pod=~\"api-v1-.*\",container!=\"\"}[3m] @ $END)) / 2^20"
echo "== control plane linkerd: CPU millicores / RAM MiB"
prom "sum(rate(container_cpu_usage_seconds_total{namespace=\"linkerd\",container!=\"\"}[3m] @ $END)) * 1000 or vector(0)"
prom "sum(avg_over_time(container_memory_working_set_bytes{namespace=\"linkerd\",container!=\"\"}[3m] @ $END)) / 2^20 or vector(0)"
