#!/usr/bin/env bash
# usage: run-k6.sh SCRIPT TESTID [RATE] [DURATION] [MESH=true|false]
set -e
SCRIPT=$1; TESTID=$2; RATE=${3:-20}; DUR=${4:-5m}; MESH=${5:-false}
kubectl create configmap k6-scripts -n loadtest --from-file=$HOME/containers/shop/loadtest/ \
  --dry-run=client -o yaml | kubectl apply -f - >/dev/null
kubectl delete job k6-$TESTID -n loadtest --ignore-not-found >/dev/null
ANN='{}'
[ "$MESH" = true ] && ANN='{"linkerd.io/inject":"enabled","config.alpha.linkerd.io/proxy-enable-native-sidecar":"true"}'
cat <<EOF | kubectl apply -f -
apiVersion: batch/v1
kind: Job
metadata: { name: k6-$TESTID, namespace: loadtest }
spec:
  backoffLimit: 0
  template:
    metadata:
      annotations: $ANN
    spec:
      restartPolicy: Never
      containers:
        - name: k6
          image: grafana/k6:0.54.0
          args: ["run", "-o", "experimental-prometheus-rw", "--summary-trend-stats", "avg,min,med,p(95),p(99),max", "--tag", "testid=$TESTID", "/scripts/$SCRIPT"]
          env:
            - { name: K6_PROMETHEUS_RW_SERVER_URL, value: "http://kps-prometheus.monitoring.svc:9090/api/v1/write" }
            - { name: K6_PROMETHEUS_RW_TREND_STATS, value: "p(50),p(95),p(99),avg" }
            - { name: RATE, value: "$RATE" }
            - { name: DURATION, value: "$DUR" }
          volumeMounts: [{ name: scripts, mountPath: /scripts }]
      volumes: [{ name: scripts, configMap: { name: k6-scripts } }]
EOF
echo "logs: kubectl logs -n loadtest job/k6-$TESTID -f"
