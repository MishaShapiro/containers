"""Canary gate: раз в INTERVAL секунд читает здоровье v2 из Prometheus и двигает вес v2 в HTTPRoute."""
import logging
import math
import os
import time

import requests
from kubernetes import client, config
from prometheus_client import Gauge, start_http_server

PROM = os.getenv("PROM_URL", "http://kps-prometheus.monitoring.svc:9090")
NS = os.getenv("NAMESPACE", "shop")
ROUTE = os.getenv("ROUTE", "api")
CANARY = os.getenv("CANARY_BACKEND", "api-v2")
INTERVAL = float(os.getenv("INTERVAL", "15"))
START = int(os.getenv("START_WEIGHT", "10"))
STEP = int(os.getenv("STEP", "20"))
CHECKS_PER_STEP = int(os.getenv("CHECKS_PER_STEP", "2"))
MAX_ERR = float(os.getenv("MAX_ERROR_RATIO", "0.05"))
MAX_P95 = float(os.getenv("MAX_P95_SECONDS", "0.5"))
MIN_RPS = float(os.getenv("MIN_RPS", "0.2"))
# прогрев: метрики за 1m должны относиться к новым подам v2, а не к старым из предыдущего rollout
WARMUP = float(os.getenv("WARMUP_SECONDS", "75"))
# «голодание»: трафик есть, а до v2 доходит < 1/4 положенной доли — эндпоинт выбит circuit breaker'ом или не готов
STARVE_CHECKS = int(os.getenv("STARVE_CHECKS", "4"))

GROUP, VER, PLURAL = "gateway.networking.k8s.io", "v1", "httproutes"
SEL = f'namespace="{NS}",version="v2",path="/order"'
Q_TOTAL = f'sum(rate(http_requests_total{{namespace="{NS}",path="/order"}}[1m]))'
Q_RPS = f"sum(rate(http_requests_total{{{SEL}}}[1m]))"
Q_ERR = (f'(sum(rate(http_requests_total{{{SEL},status=~"5.."}}[1m])) or vector(0))'
         f" / sum(rate(http_requests_total{{{SEL}}}[1m]))")
Q_P95 = f"histogram_quantile(0.95, sum by (le) (rate(http_request_duration_seconds_bucket{{{SEL}}}[1m])))"

STATES = {"canary": 0, "promoted": 1, "rolled_back": 2}
G_WEIGHT = Gauge("gate_v2_weight", "Current v2 traffic weight, %")
G_ERR = Gauge("gate_v2_error_ratio", "Observed v2 error ratio")
G_P95 = Gauge("gate_v2_p95_seconds", "Observed v2 p95 latency")
G_STATE = Gauge("gate_state", "0=canary 1=promoted 2=rolled_back")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("gate")


def query(expr):
    r = requests.get(f"{PROM}/api/v1/query", params={"query": expr}, timeout=5)
    r.raise_for_status()
    res = r.json()["data"]["result"]
    if not res:
        return None
    v = float(res[0]["value"][1])
    return None if math.isnan(v) else v


def set_weight(api, w2):
    route = api.get_namespaced_custom_object(GROUP, VER, NS, PLURAL, ROUTE)
    for ref in route["spec"]["rules"][0]["backendRefs"]:
        ref["weight"] = w2 if ref["name"] == CANARY else 100 - w2
    api.replace_namespaced_custom_object(GROUP, VER, NS, PLURAL, ROUTE, route)
    G_WEIGHT.set(w2)
    log.info("weight v2 -> %d%%", w2)


def main():
    config.load_incluster_config()
    api = client.CustomObjectsApi()
    start_http_server(8000)
    weight, state, healthy, starved = START, "canary", 0, 0
    set_weight(api, weight)
    G_STATE.set(STATES[state])
    log.info("warmup %.0fs", WARMUP)
    time.sleep(WARMUP)
    while True:
        time.sleep(INTERVAL)
        if state != "canary":
            continue
        try:
            rps, err, p95, total = query(Q_RPS), query(Q_ERR), query(Q_P95), query(Q_TOTAL)
        except Exception as e:
            log.warning("prometheus query failed: %s", e)
            continue
        G_ERR.set(err or 0)
        G_P95.set(p95 or 0)
        if rps is None or rps < MIN_RPS:
            expected = (total or 0) * weight / 100
            if expected >= 4 * MIN_RPS and (rps or 0) < expected / 4:
                starved += 1
                log.info("v2 starved: rps=%.2f, expected ~%.2f (%d/%d)", rps or 0, expected, starved, STARVE_CHECKS)
                if starved >= STARVE_CHECKS:
                    log.info("UNHEALTHY v2 gets no traffic (circuit breaker?) -> rollback")
                    weight, state = 0, "rolled_back"
                    set_weight(api, weight)
                    G_STATE.set(STATES[state])
            else:
                log.info("not enough v2 traffic (rps=%s), holding", rps)
            continue
        starved = 0
        if (err or 0) > MAX_ERR or (p95 or 0) > MAX_P95:
            log.info("UNHEALTHY err=%.3f p95=%.3fs -> rollback", err or 0, p95 or 0)
            weight, state = 0, "rolled_back"
            set_weight(api, weight)
        else:
            healthy += 1
            log.info("healthy check %d/%d err=%.3f p95=%.3fs", healthy, CHECKS_PER_STEP, err or 0, p95 or 0)
            if healthy >= CHECKS_PER_STEP:
                healthy = 0
                weight = min(100, weight + STEP)
                set_weight(api, weight)
                if weight == 100:
                    state = "promoted"
                    log.info("PROMOTED")
        G_STATE.set(STATES[state])


if __name__ == "__main__":
    main()
