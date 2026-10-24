#!/usr/bin/env bash
# usage: deploy.sh <3|4|5|6> [доп. аргументы helm, например --set batch.replicas=10]
set -euo pipefail
N=${1:?укажи номер лабы: 3, 4, 5 или 6}; shift
C=~/containers
declare -A OVERLAY=(
  [4]=$C/lecture-4-scheduling-resources/values-lab4.yaml
  [5]=$C/lecture-5-kubernetes-networking/values-lab5.yaml
  [6]=$C/lecture-6-service-mesh/values-lab6.yaml
)
args=()
for i in 4 5 6; do
  if [ "$i" -le "$N" ] && [ -f "${OVERLAY[$i]}" ]; then
    args+=(-f "${OVERLAY[$i]}")
  fi
done
# --reset-values: каждый запуск собирает values заново (база + overlay-файлы + "$@").
# Без него Helm при пустых -f/--set переиспользует значения прошлой ревизии, и старый --set "прилипает"
echo "+ helm upgrade --install shop $C/shop/chart/shop -n shop --reset-values ${args[*]} $*"
helm upgrade --install shop "$C/shop/chart/shop" -n shop --create-namespace --reset-values "${args[@]}" "$@"
