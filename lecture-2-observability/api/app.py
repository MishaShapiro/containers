import json
import logging
import os
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from flask import Flask, Response, g, jsonify, request
from opentelemetry import context as otel_context
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

PORT = int(os.getenv("PORT", "8080"))
SERVICE = os.getenv("OTEL_SERVICE_NAME", "api")

# --- трейсы: провайдер + OTLP-экспортёр (адрес берётся из OTEL_EXPORTER_OTLP_ENDPOINT) ---
provider = TracerProvider(resource=Resource.create({"service.name": SERVICE}))
if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(SERVICE)


# --- логи: JSON в stdout, в каждой строке trace_id текущего спана ---
class JsonFormatter(logging.Formatter):
    def format(self, record):
        ctx = trace.get_current_span().get_span_context()
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "msg": record.getMessage(),
            "trace_id": format(ctx.trace_id, "032x") if ctx.is_valid else None,
            "span_id": format(ctx.span_id, "016x") if ctx.is_valid else None,
        }
        entry.update(getattr(record, "fields", {}))
        return json.dumps(entry)


log = logging.getLogger("api")
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
log.addHandler(_handler)
log.setLevel(logging.INFO)
log.propagate = False

# --- метрики RED ---
REQUESTS = Counter("http_requests_total", "HTTP requests", ["method", "path", "status"])
ERRORS = Counter("http_request_errors_total", "HTTP 5xx responses", ["path"])
LATENCY = Histogram(
    "http_request_duration_seconds", "Request latency", ["path"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2, 3, 5),
)

app = Flask(__name__)
FlaskInstrumentor().instrument_app(app, excluded_urls="metrics,health")
RequestsInstrumentor().instrument()


@app.before_request
def _start_timer():
    g.start = time.perf_counter()


@app.after_request
def _observe(resp):
    path = request.url_rule.rule if request.url_rule else "unknown"
    if path == "/metrics":
        return resp
    elapsed = time.perf_counter() - g.start
    REQUESTS.labels(request.method, path, str(resp.status_code)).inc()
    LATENCY.labels(path).observe(elapsed)
    if resp.status_code >= 500:
        ERRORS.labels(path).inc()
    level = logging.ERROR if resp.status_code >= 500 else logging.INFO
    log.log(level, "request handled", extra={"fields": {
        "method": request.method, "path": path,
        "status": resp.status_code, "duration_ms": round(elapsed * 1000, 1),
    }})
    return resp


@app.get("/health")
def health():
    return "ok"


@app.get("/fail")
def fail():
    span = trace.get_current_span()
    span.set_status(Status(StatusCode.ERROR, "simulated failure"))
    span.set_attribute("error.kind", "simulated")
    return jsonify(error="simulated failure"), 500


@app.get("/slow")
def slow():
    with tracer.start_as_current_span("slow-op") as span:
        delay = random.uniform(1, 3)
        span.set_attribute("slow.delay_s", round(delay, 2))
        time.sleep(delay)
    return jsonify(slept=round(delay, 2))


@app.get("/load")
def load():
    n = int(request.args.get("n", 100))
    ctx = otel_context.get_current()  # передаём контекст трейса в потоки, чтобы подзапросы стали дочерними спанами

    def hit(_):
        token = otel_context.attach(ctx)
        try:
            return requests.get(f"http://127.0.0.1:{PORT}/health", timeout=5).status_code
        except requests.RequestException:
            return 0
        finally:
            otel_context.detach(token)

    with ThreadPoolExecutor(max_workers=20) as pool:
        codes = list(pool.map(hit, range(n)))
    return jsonify(sent=n, ok=codes.count(200))


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
