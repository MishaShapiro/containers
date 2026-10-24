#!/usr/bin/env bash
# mydocker.sh — запустить команду в своих namespaces, с cgroup-лимитами и урезанными правами.
# usage: sudo [MEM=100M] [CPU="50000 100000"] [PIDS=64] ./mydocker.sh /opt/mydocker/api
set -euo pipefail
[ "$(id -u)" = 0 ] || { echo "запускай через sudo" >&2; exit 1; }
[ $# -ge 1 ] || { echo "usage: $0 <cmd> [args...]" >&2; exit 1; }

HERE=$(cd "$(dirname "$0")" && pwd)
MEM=${MEM:-100M}
CPU=${CPU:-"50000 100000"}
PIDS=${PIDS:-64}
ID=$$
CG_ROOT=/sys/fs/cgroup/mydocker
CG=$CG_ROOT/c$ID
VH=vh$ID                      # конец veth на хосте
VC=vc$ID                      # конец veth для контейнера (внутри переименуем в eth0)
HOST_IP=10.200.0.1
CT_IP=10.200.0.2

cleanup() {
  ip link del "$VH" 2>/dev/null || true
  rmdir "$CG" 2>/dev/null || true
}
trap cleanup EXIT

# --- 1. cgroup ---
mkdir -p "$CG_ROOT"
echo "+memory +cpu +pids" > "$CG_ROOT/cgroup.subtree_control"
mkdir -p "$CG"
echo "$MEM"  > "$CG/memory.max"
echo 0       > "$CG/memory.swap.max"
echo "$CPU"  > "$CG/cpu.max"
echo "$PIDS" > "$CG/pids.max"

# --- 2-3. в cgroup, затем namespaces ---
install -m 0755 "$HERE/inside.sh" /opt/mydocker/inside.sh
(
  echo "$BASHPID" > "$CG/cgroup.procs"
  # --map-users только пишет карту uid. Сам процесс снаружи остаётся uid 0, а 0 в карту не входит,
  # поэтому внутри он оказался бы nobody. --setuid/--setgid 0 делают его root внутри (= 100000 снаружи)
  exec unshare --user --map-users=0:100000:65536 --map-groups=0:100000:65536 \
       --setuid=0 --setgid=0 \
       --pid --fork --mount-proc --uts --ipc --net --cgroup \
       /opt/mydocker/inside.sh "$@"
) &
CPID=$!

# ждём, пока процесс окажется в новом net ns
for _ in $(seq 50); do
  [ "$(readlink /proc/$CPID/ns/net)" != "$(readlink /proc/self/ns/net)" ] && break
  sleep 0.05
done

# --- 4. сеть: veth-пара хост <-> контейнер ---
ip link add "$VH" type veth peer name "$VC"
ip link set "$VC" netns "$CPID"
ip addr add "$HOST_IP/24" dev "$VH"
ip link set "$VH" up
nsenter -t "$CPID" -n sh -c "
  ip link set lo up
  ip link set $VC name eth0
  ip addr add $CT_IP/24 dev eth0
  ip link set eth0 up
  ip route add default via $HOST_IP"

echo "container up: cgroup=$CG  ip=$CT_IP  (Ctrl+C — остановить)"
wait "$CPID"
