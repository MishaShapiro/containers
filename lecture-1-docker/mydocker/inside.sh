#!/bin/bash
set -e
hostname mydocker

# ждём, пока хост перекинет к нам конец veth и настроит его
for _ in $(seq 50); do
  ip -o addr show eth0 2>/dev/null | grep -q 'inet ' && break
  sleep 0.1
done

# 1) uid/gid 1000 внутри (снаружи это 101000), 2) ни одной capability, 3) no_new_privs,
# 4) seccomp-фильтр, 5) exec сервиса — он станет PID 1
exec setpriv --reuid=1000 --regid=1000 --clear-groups \
     --inh-caps=-all --bounding-set=-all --no-new-privs \
     /opt/mydocker/seccomp-exec /opt/mydocker/seccomp.profile "$@"
