#!/usr/bin/env bash
# Применяет одну случайную сетевую поломку через values чарта. Какая — не говорит.
set -e
variants=(
  "--set networkPolicy.dns.enabled=false"                    # нет разрешения DNS
  "--set networkPolicy.postgres.allowFrom={api-svc,worker}"  # неверная метка в allow-правиле
  "--set networkPolicy.postgres.port=5433"                   # порт в правиле не совпадает с портом сервиса
  "--set networkPolicy.overbroadDeny.enabled=true"           # слишком широкое deny-правило
)
i=$((RANDOM % ${#variants[@]}))
echo "$i ${variants[$i]}" | base64 > ~/.shop-breakage       # «запечатанный конверт» для проверки
# то же, что обычный deploy (база + lab4 + lab5), плюс одна поломка поверх; values-lab5.yaml не меняется
~/containers/shop/scripts/deploy.sh 5 ${variants[$i]} >/dev/null
# Cilium не рвёт уже установленные соединения (conntrack), поэтому перезапуск: новые соединения пойдут по новым правилам
kubectl rollout restart deploy/api deploy/worker -n shop >/dev/null
kubectl rollout status deploy/api -n shop >/dev/null
echo "Поломка применена."
