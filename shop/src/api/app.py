import logging
import os
import random
import threading
import time

from flask import Flask, Response, g, jsonify, request
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from psycopg_pool import ConnectionPool

VERSION = os.getenv("VERSION", "v1")
DB_URL = os.getenv("DATABASE_URL", "")
FLAKY_RATE = float(os.getenv("FLAKY_RATE", "0.3"))


def flag(name):
    return os.getenv(name, "false").lower() == "true"


SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id           BIGSERIAL PRIMARY KEY,
    item         TEXT        NOT NULL,
    qty          INT         NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed    BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
)"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("api")

REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status", "version"])
LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency", ["path", "version"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.2, 0.3, 0.5, 1, 2, 5),
)

_pool = None
_pool_lock = threading.Lock()


def db():
    """Пул открывается лениво: api стартует и отвечает на /health даже без БД."""
    global _pool
    if not DB_URL:
        raise RuntimeError("DATABASE_URL is not set")
    with _pool_lock:
        if _pool is None:
            pool = ConnectionPool(DB_URL, min_size=1, max_size=10, kwargs={"autocommit": True})
            try:
                with pool.connection() as conn:
                    conn.execute(SCHEMA)
            except Exception:
                pass  # таблицу мог параллельно создать worker
            _pool = pool
    return _pool


app = Flask(__name__)


@app.before_request
def _start():
    g.start = time.perf_counter()


@app.after_request
def _observe(resp):
    path = request.url_rule.rule if request.url_rule else "unknown"
    if path != "/metrics":
        REQUESTS.labels(request.method, path, str(resp.status_code), VERSION).inc()
        LATENCY.labels(path, VERSION).observe(time.perf_counter() - g.start)
    return resp


def chaos():
    """Искусственные сбои для лабы 6."""
    if flag("FAIL"):
        return jsonify(error="FAIL=true", version=VERSION), 500
    if flag("FLAKY") and random.random() < FLAKY_RATE:
        return jsonify(error="flaky", version=VERSION), 500
    return None


@app.get("/health")
def health():
    if flag("HEALTH_FAIL"):
        return "unhealthy", 503
    return "ok"


@app.get("/version")
def version():
    return jsonify(version=VERSION)


@app.post("/order")
def create_order():
    if (bad := chaos()) is not None:
        return bad
    body = request.get_json(silent=True) or {}
    item, qty = body.get("item", "widget"), int(body.get("qty", 1))
    try:
        with db().connection() as conn:
            row = conn.execute(
                "INSERT INTO orders (item, qty) VALUES (%s, %s) RETURNING id", (item, qty)
            ).fetchone()
    except Exception as e:
        log.error("db error: %s", e)
        return jsonify(error="db unavailable"), 503
    return jsonify(id=row[0], version=VERSION), 201


@app.get("/orders")
def list_orders():
    if (bad := chaos()) is not None:
        return bad
    try:
        with db().connection() as conn:
            rows = conn.execute(
                "SELECT id, item, qty, processed, created_at FROM orders ORDER BY id DESC LIMIT 50"
            ).fetchall()
    except Exception as e:
        log.error("db error: %s", e)
        return jsonify(error="db unavailable"), 503
    return jsonify(version=VERSION, orders=[
        {"id": r[0], "item": r[1], "qty": r[2], "processed": r[3], "created_at": r[4].isoformat()}
        for r in rows
    ])


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
