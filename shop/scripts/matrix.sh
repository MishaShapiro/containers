#!/usr/bin/env bash
# Проверка матрицы: TCP-подключение из каждого источника к каждому адресату.
NS=shop
DB=shop-db-rw
PYPROBE='import socket,sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), timeout=3)'

probe() {   # ns  pod/deploy  container  host  port
  kubectl exec -n "$1" "$2" -c "$3" -- python -c "$PYPROBE" "$4" "$5" >/dev/null 2>&1 && echo OPEN || echo BLOCKED
}
probe_pg() { # postgres-контейнер без python: используем bash /dev/tcp
  kubectl exec -n $NS shop-db-1 -c postgres -- bash -c "timeout 3 bash -c '</dev/tcp/$1/$2'" >/dev/null 2>&1 && echo OPEN || echo BLOCKED
}

API=api.$NS.svc.cluster.local; WRK=worker.$NS.svc.cluster.local; PG=$DB.$NS.svc.cluster.local
INET=1.1.1.1

printf "%-26s %-22s %-9s %-9s %s\n" FROM TO EXPECTED ACTUAL RESULT
row() { # from to expected actual
  [ "$3" = "$4" ] && r="✅" || r="❌ MISMATCH"
  printf "%-26s %-22s %-9s %-9s %s\n" "$1" "$2" "$3" "$4" "$r"
}

row "loadtest/client"  "api:8080"      OPEN    "$(probe loadtest pod/client client $API 8080)"
row "loadtest/client"  "worker:8080"   BLOCKED "$(probe loadtest pod/client client $WRK 8080)"
row "loadtest/client"  "postgres:5432" BLOCKED "$(probe loadtest pod/client client $PG 5432)"
row "api"              "postgres:5432" OPEN    "$(probe $NS deploy/api api $PG 5432)"
row "api"              "worker:8080"   BLOCKED "$(probe $NS deploy/api api $WRK 8080)"
row "api"              "internet:443"  BLOCKED "$(probe $NS deploy/api api $INET 443)"
row "worker"           "postgres:5432" OPEN    "$(probe $NS deploy/worker worker $PG 5432)"
row "worker"           "api:8080"      BLOCKED "$(probe $NS deploy/worker worker $API 8080)"
row "worker"           "internet:443"  BLOCKED "$(probe $NS deploy/worker worker $INET 443)"
row "intruder"         "postgres:5432" BLOCKED "$(probe $NS pod/intruder c $PG 5432)"
row "intruder"         "api:8080"      BLOCKED "$(probe $NS pod/intruder c $API 8080)"
row "intruder"         "worker:8080"   BLOCKED "$(probe $NS pod/intruder c $WRK 8080)"
row "postgres"         "api:8080"      BLOCKED "$(probe_pg $API 8080)"
row "postgres"         "internet:443"  BLOCKED "$(probe_pg $INET 443)"
