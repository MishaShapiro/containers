import logging
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import psycopg
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

DB_URL = os.getenv("DATABASE_URL", "")
INTERVAL = float(os.getenv("POLL_INTERVAL", "2"))
BATCH = int(os.getenv("BATCH_SIZE", "10"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders (
    id           BIGSERIAL PRIMARY KEY,
    item         TEXT        NOT NULL,
    qty          INT         NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    processed    BOOLEAN     NOT NULL DEFAULT false,
    processed_at TIMESTAMPTZ
)"""
# SKIP LOCKED: два worker-а не схватят один и тот же заказ
CLAIM = """
UPDATE orders SET processed = true, processed_at = now()
WHERE id IN (SELECT id FROM orders WHERE NOT processed ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED)
RETURNING id"""

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")

PROCESSED = Counter("shop_orders_processed_total", "Orders processed by worker")
PENDING = Gauge("shop_orders_pending", "Orders waiting for processing")
LAST_OK = Gauge("shop_worker_last_success_timestamp_seconds", "Last successful DB poll")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            body, ctype, code = b"ok", "text/plain", 200
        elif self.path == "/metrics":
            body, ctype, code = generate_latest(), CONTENT_TYPE_LATEST, 200
        else:
            body, ctype, code = b"not found", "text/plain", 404
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def loop():
    conn = None
    while True:
        try:
            if not DB_URL:
                log.warning("DATABASE_URL is not set, waiting")
            else:
                if conn is None or conn.closed:
                    conn = psycopg.connect(DB_URL, autocommit=True, connect_timeout=5)
                    try:
                        conn.execute(SCHEMA)
                    except Exception:
                        pass
                with conn.transaction():
                    done = conn.execute(CLAIM, (BATCH,)).fetchall()
                if done:
                    PROCESSED.inc(len(done))
                    log.info("processed %d orders", len(done))
                PENDING.set(conn.execute("SELECT count(*) FROM orders WHERE NOT processed").fetchone()[0])
                LAST_OK.set_to_current_time()
        except Exception as e:
            log.error("poll failed: %s", e)
            try:
                conn and conn.close()
            except Exception:
                pass
            conn = None
        time.sleep(INTERVAL)


if __name__ == "__main__":
    threading.Thread(target=loop, daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
