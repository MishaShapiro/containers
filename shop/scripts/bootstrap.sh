#!/usr/bin/env bash
# usage: bootstrap.sh [N]   N — до какой лабы применить overlay-файлы чарта shop (по умолчанию 4)
set -euo pipefail
C=~/containers
LAB2=$C/lecture-2-observability
SHOP=$C/shop
LAB=${1:-4}
FULL_STACK=${FULL_STACK:-false}

ns() { kubectl create namespace "$1" --dry-run=client -o yaml | kubectl apply -f -; }

# --- стек мониторинга (лаба 2) ---
ns monitoring
helm upgrade --install kps prometheus-community/kube-prometheus-stack -n monitoring -f $LAB2/values/kps.yaml --wait
helm upgrade --install karma wiremind/karma -n monitoring -f $LAB2/values/karma.yaml
if [ "$FULL_STACK" = true ]; then
  helm upgrade --install loki  grafana/loki  -n monitoring -f $LAB2/values/loki.yaml
  helm upgrade --install alloy grafana/alloy -n monitoring -f $LAB2/values/alloy.yaml
  helm upgrade --install jaeger jaegertracing/jaeger -n monitoring -f $LAB2/values/jaeger.yaml --version 3.4.1
fi
# приёмник алертов из чарта лабы 2 (сам api из лабы 2 не нужен)
helm upgrade --install api $LAB2/chart/api -n demo --create-namespace --set replicas=0

# --- ограждения (лаба 3), облегчённая установка ---
helm upgrade --install kyverno kyverno/kyverno -n kyverno --create-namespace --wait \
  --set admissionController.replicas=1 \
  --set backgroundController.enabled=false \
  --set cleanupController.enabled=false \
  --set reportsController.enabled=false
kubectl apply -f $SHOP/policies/kyverno/

# --- оператор БД ---
helm upgrade --install cnpg cnpg/cloudnative-pg -n cnpg-system --create-namespace --wait

# --- образы ---
for svc in api worker batch gate; do
  [ -d $SHOP/src/$svc ] || continue
  docker build -t shop.local/$svc:1.0 $SHOP/src/$svc
  minikube image load shop.local/$svc:1.0
done
# после rolling update в лабе 3 в базовом values у api tag "1.1" — тот же код под вторым тегом
docker tag shop.local/api:1.0 shop.local/api:1.1
minikube image load shop.local/api:1.1

# --- shop: база + overlay-файлы лаб до $LAB ---
ns shop; ns loadtest
$SHOP/scripts/deploy.sh "$LAB"
