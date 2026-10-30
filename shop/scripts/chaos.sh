#!/usr/bin/env bash
# Раз в INTERVAL секунд убивает случайный Running-под api или worker
NS=${NS:-shop}
INTERVAL=${INTERVAL:-6}
while true; do
  pod=$(kubectl get pods -n "$NS" -l 'app.kubernetes.io/name in (api,worker)' \
        --field-selector=status.phase=Running -o name | shuf -n1)
  [ -n "$pod" ] && echo "$(date +%T) kill $pod" && kubectl delete -n "$NS" "$pod" --wait=false >/dev/null
  sleep "$INTERVAL"
done
