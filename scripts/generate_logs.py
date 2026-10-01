#!/usr/bin/env python3
"""Generate the synthetic incident dataset for the RCA MVP.

One command builds every case (failure incidents + normal cases):

    python scripts/generate_logs.py [--seed 42] [--incidents-per-scenario 10]
                                    [--normal-cases 5] [--output-dir data]

Outputs, all linked by ``incident_id``:

    <output>/raw/incidents/INC-XXX.json   incident context + ground truth
    <output>/raw/logs/INC-XXX.jsonl       structured JSON logs (one record per line)
    <output>/raw/metrics/INC-XXX.csv      1-minute metrics for every service
    <output>/generated/manifest.json      seed, counts and SHA-256 of every file
    <output>/generated/incidents_index.csv  one summary row per case

The environment is simulated minute by minute: a fault is injected into one
component, its effect is propagated through the service call graph (latency,
timeouts, 5xx), and logs are sampled from the resulting per-minute state. Only
the standard library is used and all randomness flows from ``--seed``.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import random
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace as NS

GENERATOR_VERSION = "1.0.0"
DEFAULT_SEED = 42
DATASET_START = datetime(2026, 1, 5)

DB_POOL = "DB_CONNECTION_POOL_EXHAUSTION"
MEMORY_LEAK = "MEMORY_LEAK"
DOWNSTREAM = "DOWNSTREAM_SERVICE_TIMEOUT"
NORMAL = "NORMAL"
FAILURE_SCENARIOS = (DB_POOL, MEMORY_LEAK, DOWNSTREAM)

METRIC_COLUMNS = [
    "timestamp", "incident_id", "service", "cpu_usage", "memory_usage", "request_rate",
    "latency_ms", "error_rate", "db_connection_utilization", "downstream_latency_ms",
]
GENERATED_FILES = ("manifest.json", "incidents_index.csv")

# --------------------------------------------------------------------------- environment

# Baseline ranges per service. cpu/mem/db are percentages, rps is requests/s
# (queries/s for the database), lat is p95 latency in ms, ds is p95 latency of
# outbound calls in ms (None = service has no outbound HTTP dependencies).
SERVICES = {
    "api-gateway": {"stack": "envoy", "cpu": (12, 26), "mem": (24, 38), "rps": (220, 380),
                    "lat": (130, 220), "db": None, "ds": (110, 200), "logs_per_min": 2.2},
    "orders-api": {"stack": "python", "cpu": (22, 40), "mem": (38, 54), "rps": (70, 130),
                   "lat": (90, 170), "db": (18, 42), "ds": (60, 130), "logs_per_min": 1.8},
    "payment-api": {"stack": "java", "cpu": (18, 36), "mem": (45, 60), "rps": (25, 55),
                    "lat": (160, 280), "db": (20, 45), "ds": (130, 240), "logs_per_min": 1.6},
    "inventory-service": {"stack": "go", "cpu": (10, 24), "mem": (28, 44), "rps": (90, 170),
                          "lat": (18, 45), "db": (15, 38), "ds": (60, 140), "logs_per_min": 1.5},
    "recommendation-service": {"stack": "node", "cpu": (28, 46), "mem": (42, 58), "rps": (100, 190),
                               "lat": (55, 110), "db": (12, 30), "ds": None, "logs_per_min": 1.3},
    "database": {"stack": "postgres", "cpu": (18, 36), "mem": (58, 72), "rps": (600, 1200),
                 "lat": (2, 7), "db": (28, 46), "ds": None, "logs_per_min": 0.8},
}
# Leaves first, so a callee's state is known when its callers are simulated.
SERVICE_ORDER = ["database", "inventory-service", "recommendation-service",
                 "payment-api", "orders-api", "api-gateway"]
DB_CLIENTS = ("orders-api", "payment-api", "inventory-service", "recommendation-service")

# caller -> {callee: range for the share of caller requests that call the callee}
CALLS = {
    "orders-api": {"inventory-service": (0.55, 0.85), "payment-api": (0.2, 0.35)},
    "api-gateway": {"orders-api": (0.35, 0.5), "payment-api": (0.1, 0.2),
                    "recommendation-service": (0.3, 0.45)},
}
CALL_TIMEOUTS_MS = {
    ("orders-api", "inventory-service"): (800, 1000, 1500, 2000),
    ("orders-api", "payment-api"): (3000, 5000, 8000),
    ("api-gateway", "orders-api"): (5000, 10000, 15000),
    ("api-gateway", "payment-api"): (10000, 15000),
    ("api-gateway", "recommendation-service"): (1000, 2000, 3000),
}
# service -> (external dependency, share of requests calling it, client timeout options)
EXTERNAL_DEPS = {
    "payment-api": ("acquirer-gateway", (0.75, 0.95), (2000, 3000, 5000, 8000)),
    "inventory-service": ("warehouse-api", (0.25, 0.5), (1000, 1500, 3000)),
}
# stack -> (pool size options, connection acquisition timeout options in ms)
POOL_OPTIONS = {
    "python": ((10, 15, 20), (5000, 10000, 30000)),
    "java": ((10, 20, 30), (3000, 5000, 10000, 30000)),
    "go": ((25, 40, 50), (2000, 3000, 5000)),
    "node": ((10, 15, 20), (5000, 10000, 30000)),
}
MEMORY_LIMIT_MB = {"python": (768, 1024, 1536), "java": (1024, 1536, 2048), "go": (512, 768, 1024),
                   "node": (1536, 2048, 4096), "envoy": (512, 1024), "postgres": (8192, 16384)}

ROUTES = {
    "api-gateway": [("GET", "/api/v1/orders/{id}", "orders-api"), ("POST", "/api/v1/orders", "orders-api"),
                    ("GET", "/api/v1/cart", "orders-api"), ("POST", "/api/v1/payments", "payment-api"),
                    ("GET", "/api/v1/recommendations", "recommendation-service")],
    "orders-api": [("GET", "/api/v1/orders/{id}", ""), ("POST", "/api/v1/orders", ""),
                   ("GET", "/api/v1/cart", ""), ("PUT", "/api/v1/cart/items", "")],
    "payment-api": [("POST", "/api/v1/payments", ""), ("POST", "/api/v1/payments/{id}/capture", ""),
                    ("GET", "/api/v1/payments/{id}", ""), ("POST", "/api/v1/refunds", "")],
    "inventory-service": [("GET", "/v1/stock/{sku}", ""), ("POST", "/v1/reservations", ""),
                          ("DELETE", "/v1/reservations/{id}", "")],
    "recommendation-service": [("GET", "/recommendations/{uid}", ""),
                               ("GET", "/recommendations/{uid}/similar", "")],
}
DEP_CALLS = {
    "inventory-service": ("POST", "/v1/reservations", "reserve stock"),
    "payment-api": ("POST", "/api/v1/payments", "authorize payment"),
    "orders-api": ("GET", "/api/v1/orders/{id}", "load order"),
    "recommendation-service": ("GET", "/recommendations/{uid}", "load recommendations"),
    "acquirer-gateway": ("POST", "/v2/authorizations", "authorize card payment"),
    "warehouse-api": ("GET", "/v1/levels/{sku}", "check warehouse stock"),
}
TABLES = {"orders-api": ("orders", "order_items", "carts"), "payment-api": ("payments", "refunds", "merchants"),
          "inventory-service": ("stock_levels", "reservations"),
          "recommendation-service": ("user_events", "item_features")}
ALL_TABLES = tuple(t for ts in TABLES.values() for t in ts)
STATEMENTS = (
    "SELECT o.id, o.status FROM orders o WHERE o.customer_id = $1 ORDER BY o.created_at DESC LIMIT 20",
    "UPDATE stock_levels SET reserved = reserved + $1 WHERE sku = $2",
    "INSERT INTO payments (id, order_id, amount, currency, status) VALUES ($1, $2, $3, $4, $5)",
    "SELECT * FROM order_items WHERE order_id = ANY($1)",
    "SELECT user_id, item_id, score FROM user_events WHERE user_id = $1 AND ts > $2",
    "SELECT count(*) FROM payments WHERE merchant_id = $1 AND created_at > $2",
)

# --------------------------------------------------------------------------- log templates

# Per technology stack. "info" entries are (weight, logger, template, traced);
# every other category is a list of (logger, template). Placeholders are filled
# lazily from the per-minute service state and FIELDS below.
BANK = {
    "envoy": {
        "info": [(7, "envoy.access", '"{method} {path} HTTP/1.1" {status} upstream={upstream} duration={dur}ms', True),
                 (1, "envoy.upstream", "cluster {upstream_any}: {healthy} healthy hosts, 0 degraded", False)],
        "linked": [],
        "noise_warn": [("envoy.http", "rate limit exceeded for client {client} from {ip}, returning 429"),
                       ("envoy.connection", "TLS handshake error from {ip}: unknown certificate authority"),
                       ("envoy.access", '"{method} {path} HTTP/1.1" 404 upstream={upstream} duration={dur}ms'),
                       ("envoy.http", "downstream client {ip} closed connection before response (499) path={path}")],
        "generic_error": [("envoy.router", "upstream reset: reset reason: connection termination, cluster={upstream}"),
                          ("envoy.access", '"{method} {path} HTTP/1.1" 500 upstream={upstream} duration={dur}ms'),
                          ("envoy.router", "upstream reset: reset reason: remote reset, cluster={upstream}")],
        "generic_5xx": [("envoy.access", '"{method} {path} HTTP/1.1" 503 upstream={upstream} duration={slow_dur}ms'),
                        ("envoy.access", '"{method} {path} HTTP/1.1" 500 upstream={upstream} duration={slow_dur}ms')],
        "slow_warn": [("envoy.router", "slow upstream response from {upstream}: {slow_dur}ms for {method} {path}"),
                      ("envoy.access", '"{method} {path} HTTP/1.1" 200 upstream={upstream} duration={slow_dur}ms slow=true')],
        "timeout_error": [("envoy.router", "upstream request timeout: cluster={dep} {method} {path} after {timeout_ms}ms"),
                          ("envoy.access", '"{method} {path} HTTP/1.1" 504 upstream={dep} duration={elapsed_ms}ms'),
                          ("envoy.router", "upstream timeout (504) for {method} {path}, cluster={dep}")],
        "retry_warn": [("envoy.router", "retrying request to cluster {dep} (retry_on=5xx,reset attempt {attempt}/2)"),
                       ("envoy.router", "upstream {dep} slow: {slow_dep_ms}ms for {method} {path}")],
        "upstream_error": [("envoy.access", '"{method} {path} HTTP/1.1" 503 upstream={dep} duration={dur}ms'),
                           ("envoy.access", '"{method} {path} HTTP/1.1" 502 upstream={dep} duration={dur}ms'),
                           ("envoy.router", "upstream connect error or disconnect/reset before headers. "
                                            "reset reason: connection failure, cluster={dep}")],
        "cb_open": [("envoy.outlier", "ejecting host {host_ip} from cluster {dep}: consecutive_5xx ({fr}% failures)")],
        "cb_half": [("envoy.outlier", "host {host_ip} returned to cluster {dep} after ejection period")],
        "cb_closed": [],
        "fallback_warn": [("envoy.lua", "serving fallback response for {method} {path}: upstream {dep} unavailable"),
                          ("envoy.lua", "recommendations degraded: returning cached payload for {path}")],
        "health_ok": [("envoy.health", "health check passed for cluster {upstream_any} ({healthy}/{healthy} hosts)")],
        "health_fail": [("envoy.health", "health check failed for cluster {dep} host {host_ip}: timeout"),
                        ("envoy.health", "health check failed for cluster {dep} host {host_ip}: HTTP 503")],
        "health_fail_db": [],
    },
    "python": {
        "info": [(6, "uvicorn.access", '{ip}:0 - "{method} {path} HTTP/1.1" {status} ({dur}ms)', True),
                 (4, "app.request", "request completed method={method} path={path} status={status} duration_ms={dur}", True),
                 (2, "app.request", "request started method={method} path={path}", True),
                 (2, "app.orders", "order {order_id} created items={items} total={amount} {currency}", True),
                 (2, "app.cache", "cache hit key=cart:{uid}", True),
                 (1, "app.cache", "cache miss key=cart:{uid}, loading from database", True),
                 (2, "app.db", "database query completed table={tbl} rows={rows} duration_ms={qms}", True),
                 (1, "app.orders", "stock reservation confirmed for order {order_id} ({items} items)", True)],
        "linked": [("app.request", "request completed method={method} path={path} status={status} duration_ms={dur}")],
        "noise_warn": [("app.request", "request validation failed method={method} path={path} status=422"),
                       ("app.auth", "token for client {client} expires in {jwt_s}s, refresh recommended"),
                       ("app.request", "client disconnected before response was sent path={path}"),
                       ("app.cache", "cache miss ratio {miss_pct}% over last 60s above target 15%"),
                       ("app.db", "slow query table={tbl} duration_ms={slow_q_ms}"),
                       ("app.orders", "optimistic lock conflict on order {order_id}, retrying (attempt 2/5)"),
                       ("app.deprecation", "deprecated endpoint /api/v0/orders called by {client}")],
        "generic_error": [("app.request", "Unhandled exception in {method} {path}: KeyError('shipping_address')"),
                          ("app.request", "request failed method={method} path={path} status=500 duration_ms={dur}"),
                          ("app.events", "failed to publish order.created for {order_id}: broker ack not received"),
                          ("app.request", "Unhandled exception in {method} {path}: ValueError('invalid quantity')"),
                          ("app.orders", "failed to apply coupon for order {order_id}: malformed response from promotions")],
        "generic_5xx": [("app.request", "request failed method={method} path={path} status=503 duration_ms={slow_dur}"),
                        ("app.request", "request failed method={method} path={path} status=500 duration_ms={slow_dur}"),
                        ("app.orders", "failed to create order {order_id}: internal error"),
                        ("app.request", "Exception in ASGI application while handling {method} {path}")],
        "slow_warn": [("app.request", "slow request method={method} path={path} duration_ms={slow_dur} threshold_ms={slo_ms}"),
                      ("app.request", "request exceeded latency SLO: {method} {path} took {slow_dur}ms")],
        "db_pool_error": [("sqlalchemy.pool", "sqlalchemy.exc.TimeoutError: QueuePool limit of size {pool} overflow "
                                              "{overflow} reached, connection timed out, timeout {pool_timeout_s:.2f}"),
                          ("app.db", "could not obtain database connection within {pool_timeout_s:.0f}s "
                                     "while handling {method} {path}"),
                          ("app.orders", "failed to create order {order_id}: TimeoutError acquiring connection"),
                          ("app.db", "Database connection timeout")],
        "db_generic_error": [("app.db", "transaction rolled back for order {order_id}: OperationalError"),
                             ("app.db", "Database connection timeout"),
                             ("app.request", "request failed method={method} path={path} status=503 duration_ms={slow_dur}")],
        "db_pool_warn": [("sqlalchemy.pool", "connection checkout took {wait_ms}ms (pool size={pool}, overflow={overflow})"),
                         ("app.db", "waiting for database connection: {waiting} requests queued")],
        "pool_stats": [("app.db", "db pool stats size={pool} checked_out={active} idle={idle} waiting={waiting}")],
        "memory_warn": [("gunicorn.error", "worker pid={pid} rss={rss_mb}MiB exceeds soft limit {soft_mb}MiB"),
                        ("app.gc", "gc: collection gen={gen} took {gc_s:.2f}s, {n_objects} objects collected"),
                        ("app.request", "event loop blocked for {gc_ms}ms")],
        "memory_error": [("gunicorn.error", "[CRITICAL] WORKER TIMEOUT (pid:{pid})"),
                         ("app.request", "MemoryError while handling {method} {path}"),
                         ("app.request", "request failed method={method} path={path} status=500 duration_ms={slow_dur}")],
        "oom_fatal": [("gunicorn.error", "Worker (pid:{pid}) was sent SIGKILL! Perhaps out of memory?")],
        "mem_stats": [("app.metrics", "process stats rss={rss_mb}MiB threads={threads} open_fds={fds}")],
        "timeout_error": [("httpx", "httpx.ReadTimeout: timed out calling {dep} {dep_method} {dep_path} after {timeout_s:.1f}s"),
                          ("app.orders", "failed to {dep_action} for order {order_id}: {dep} did not respond within {timeout_ms}ms"),
                          ("app.request", "request failed method={method} path={path} status=504 duration_ms={elapsed_ms}"),
                          ("httpx", "httpx.ConnectTimeout: connection to {dep} timed out")],
        "retry_warn": [("app.client", "retrying {dep} request (attempt {attempt}/3) after ReadTimeout"),
                       ("app.client", "{dep} call took {slow_dep_ms}ms, exceeding budget {budget_ms}ms")],
        "upstream_error": [("app.client", "{dep} returned 503 Service Unavailable for {dep_method} {dep_path}"),
                           ("app.orders", "failed to {dep_action} for order {order_id}: upstream error 500 from {dep}"),
                           ("httpx", "httpx.RemoteProtocolError: server disconnected without sending a response ({dep})")],
        "cb_open": [("app.client", "circuit breaker '{dep}' opened: failure rate {fr}% over threshold 50%")],
        "cb_half": [("app.client", "circuit breaker '{dep}' half-open, allowing trial requests")],
        "cb_closed": [("app.client", "circuit breaker '{dep}' closed")],
        "health_ok": [("app.health", "health check passed (db=ok, cache=ok)")],
        "health_fail": [("app.health", "readiness check failed: timeout after 2s")],
        "health_fail_db": [("app.health", "readiness check failed: database ping exceeded 1000ms")],
        "boot": [("gunicorn.error", "Booting worker with pid: {pid}")],
    },
    "java": {
        "info": [(5, "c.s.p.web.PaymentController", "Completed {method} {path} {status} in {dur}ms", True),
                 (2, "c.s.p.web.PaymentController", "Received {method} {path}", True),
                 (3, "c.s.p.service.PaymentService", "Payment {pay_id} authorized amount={amount} currency={currency}", True),
                 (1, "c.s.p.service.PaymentService", "Payment {pay_id} captured", True),
                 (2, "c.s.p.repository.PaymentRepository", "Query payments by id completed in {qms}ms", True),
                 (1, "c.s.p.cache.MerchantConfigCache", "Merchant config cache hit (merchant=m_{merchant})", True)],
        "linked": [("c.s.p.web.PaymentController", "Completed {method} {path} {status} in {dur}ms")],
        "noise_warn": [("c.s.p.service.PaymentService", "Payment {pay_id} declined by issuer: insufficient_funds"),
                       ("c.s.p.service.FraudScreening", "Fraud score {fraud} above review threshold for payment {pay_id}"),
                       ("com.zaxxer.hikari.pool.HikariPool", "HikariPool-1 - Thread starvation or clock leap detected "
                                                             "(housekeeper delta={leap})."),
                       ("c.s.p.web.GlobalExceptionHandler", "Request validation failed for {method} {path}: currency must not be null"),
                       ("gc", "GC pause (G1 Evacuation Pause) (young) {gc_ms}ms")],
        "generic_error": [("c.s.p.web.GlobalExceptionHandler", "Unhandled exception for {method} {path}: java.lang.NullPointerException"),
                          ("c.s.p.service.WebhookPublisher", "Failed to deliver webhook for payment {pay_id}: HTTP 500 from merchant endpoint"),
                          ("c.s.p.service.RefundService", "Refund for payment {pay_id} rejected: IllegalStateException: payment not captured"),
                          ("c.s.p.web.GlobalExceptionHandler", "Unhandled exception for {method} {path}: "
                                                               "com.fasterxml.jackson.databind.JsonMappingException")],
        "generic_5xx": [("c.s.p.web.GlobalExceptionHandler", "Request {method} {path} failed with status 503"),
                        ("c.s.p.web.GlobalExceptionHandler", "Request {method} {path} failed with status 500 after {slow_dur}ms"),
                        ("c.s.p.service.PaymentService", "Failed to process payment {pay_id}: internal error")],
        "slow_warn": [("c.s.p.web.PaymentController", "Slow request {method} {path} took {slow_dur}ms (threshold {slo_ms}ms)")],
        "db_pool_error": [("com.zaxxer.hikari.pool.HikariPool", "HikariPool-1 - Connection is not available, request timed out "
                                                                "after {pool_timeout_ms}ms."),
                          ("o.s.orm.jpa.JpaTransactionManager", "Could not open JPA EntityManager for transaction; nested exception "
                                                                "is org.hibernate.exception.JDBCConnectionException: Unable to acquire JDBC Connection"),
                          ("c.s.p.service.PaymentService", "Failed to process payment {pay_id}: CannotCreateTransactionException"),
                          ("o.h.engine.jdbc.spi.SqlExceptionHelper", "SQL Error: 0, SQLState: 08001 - Database connection timeout")],
        "db_generic_error": [("c.s.p.service.PaymentService", "Failed to persist payment {pay_id}: transaction rolled back"),
                             ("o.h.engine.jdbc.spi.SqlExceptionHelper", "Database connection timeout"),
                             ("c.s.p.web.GlobalExceptionHandler", "Request {method} {path} failed with status 503")],
        "db_pool_warn": [("com.zaxxer.hikari.pool.HikariPool", "HikariPool-1 - Connection acquisition took {wait_ms}ms "
                                                               "(active={active}, waiting={waiting})"),
                         ("c.s.p.repository.PaymentRepository", "Slow repository call findByIdempotencyKey took {slow_dur}ms")],
        "pool_stats": [("com.zaxxer.hikari.pool.HikariPool", "HikariPool-1 - Pool stats (total={pool}, active={active}, "
                                                             "idle={idle}, waiting={waiting})")],
        "memory_warn": [("gc", "GC pause (G1 Evacuation Pause) (young) {gc_ms}ms"),
                        ("gc", "Pause Full (G1 Compaction Pause) {heap_before}M->{heap_after}M({heap_max_mb}M) {full_gc_ms}ms"),
                        ("c.s.p.monitoring.HeapMonitor", "Heap usage at {mem_pct}% after GC (threshold 80%)")],
        "memory_error": [("c.s.p.web.GlobalExceptionHandler", "java.lang.OutOfMemoryError: Java heap space"),
                         ("o.a.c.c.C.[Tomcat].[localhost]", "Servlet.service() for servlet [dispatcherServlet] threw exception: "
                                                            "java.lang.OutOfMemoryError: GC overhead limit exceeded"),
                         ("c.s.p.web.GlobalExceptionHandler", "Request {method} {path} failed with status 500 after {slow_dur}ms")],
        "oom_fatal": [("c.s.p.PaymentApplication", "Terminating due to java.lang.OutOfMemoryError: Java heap space")],
        "mem_stats": [("gc", "GC pause (G1 Evacuation Pause) (young) {gc_ms}ms")],
        "timeout_error": [("c.s.p.client.AcquirerClient", "java.net.SocketTimeoutException: Read timed out calling {dep} "
                                                          "{dep_method} {dep_path} (timeout={timeout_ms}ms)"),
                          ("c.s.p.service.PaymentService", "Authorization for payment {pay_id} failed: upstream timeout from {dep}"),
                          ("c.s.p.web.GlobalExceptionHandler", "Request {method} {path} failed with status 504 after {elapsed_ms}ms")],
        "retry_warn": [("i.g.r.retry.Retry", "Retry '{dep}' attempt {attempt} of 3 after SocketTimeoutException"),
                       ("c.s.p.client.AcquirerClient", "Call to {dep} took {slow_dep_ms}ms")],
        "upstream_error": [("c.s.p.client.AcquirerClient", "{dep} responded 503 for {dep_method} {dep_path}"),
                           ("c.s.p.service.PaymentService", "Payment {pay_id} failed: {dep} returned HTTP 502")],
        "cb_open": [("i.g.r.circuitbreaker.CircuitBreaker", "CircuitBreaker '{dep}' changed state from CLOSED to OPEN "
                                                            "(failure rate {fr}%)")],
        "cb_half": [("i.g.r.circuitbreaker.CircuitBreaker", "CircuitBreaker '{dep}' changed state from OPEN to HALF_OPEN")],
        "cb_closed": [("i.g.r.circuitbreaker.CircuitBreaker", "CircuitBreaker '{dep}' changed state from HALF_OPEN to CLOSED")],
        "health_ok": [("o.s.b.a.health.HealthEndpoint", "Health check UP (db: UP, diskSpace: UP)")],
        "health_fail": [("o.s.b.a.health.HealthEndpoint", "Health check DOWN: livenessState BROKEN"),
                        ("o.s.b.a.health.HealthEndpoint", "Health check timed out after 3000ms")],
        "health_fail_db": [("o.s.b.a.health.HealthEndpoint", "Health check DOWN: db status DOWN (validation query timed out)")],
        "boot": [("c.s.p.PaymentApplication", "Started PaymentApplication in {boot_s:.1f} seconds")],
    },
    "go": {
        "info": [(5, "http", "request completed method={method} path={path} status={status} dur={dur}ms", True),
                 (3, "store", "stock reserved sku={sku} qty={qty} reservation=res_{hex8}", True),
                 (2, "store", "stock level read sku={sku} available={avail}", True),
                 (2, "db", "query ok stmt=select_stock rows={rows} dur={qms}ms", True),
                 (1, "cache", "local cache hit sku={sku}", True)],
        "linked": [("http", "request completed method={method} path={path} status={status} dur={dur}ms")],
        "noise_warn": [("store", "reservation res_{hex8} expired before confirmation, releasing {qty} units"),
                       ("http", "client canceled request path={path} after {dur}ms"),
                       ("warehouse", "warehouse sync lag {sync_lag}s above target 30s"),
                       ("store", "stock level for sku={sku} below reorder threshold")],
        "generic_error": [("http", 'request failed method={method} path={path} status=500 err="invalid reservation state"'),
                          ("store", "release reservation res_{hex8}: row not found"),
                          ("store", 'reserve stock sku={sku}: pq: duplicate key value violates unique constraint "reservations_pkey"')],
        "generic_5xx": [("http", "request failed method={method} path={path} status=503 dur={slow_dur}ms"),
                        ("http", "request failed method={method} path={path} status=500 dur={slow_dur}ms")],
        "slow_warn": [("http", "slow request method={method} path={path} dur={slow_dur}ms")],
        "db_pool_error": [("db", "failed to acquire connection: context deadline exceeded (max_open={pool}, in_use={active}, "
                                 "wait_count={wait_count})"),
                          ("store", "reserve stock sku={sku}: timeout waiting for database connection after {pool_timeout_ms}ms"),
                          ("db", "Database connection timeout")],
        "db_generic_error": [("store", "reserve stock sku={sku}: context deadline exceeded"),
                             ("http", "request failed method={method} path={path} status=503 dur={slow_dur}ms")],
        "db_pool_warn": [("db", "connection wait {wait_ms}ms exceeded threshold 200ms")],
        "pool_stats": [("db", "db stats open={pool} in_use={active} idle={idle} wait_count={wait_count}")],
        "memory_warn": [("runtime", "heap in use {heap_mb}MiB, next GC target {next_gc_mb}MiB, goroutines={goroutines}"),
                        ("runtime", "GC assist time high: {gc_ms}ms in last cycle")],
        "memory_error": [("runtime", "allocation failed: cannot allocate memory"),
                         ("http", "request failed method={method} path={path} status=500 dur={slow_dur}ms")],
        "oom_fatal": [("runtime", "fatal error: runtime: out of memory")],
        "mem_stats": [("runtime", "memstats heap_inuse={heap_mb}MiB sys={sys_mb}MiB num_gc={num_gc} goroutines={goroutines}")],
        "timeout_error": [("warehouse", 'warehouse lookup failed: Get "https://{dep}/v1/levels/{sku}": context deadline exceeded '
                                        "(Client.Timeout exceeded while awaiting headers)"),
                          ("store", "stock check sku={sku} failed: {dep} timeout after {timeout_ms}ms"),
                          ("http", "request failed method={method} path={path} status=504 dur={elapsed_ms}ms")],
        "retry_warn": [("warehouse", "retrying {dep} request attempt={attempt} backoff={backoff_ms}ms"),
                       ("warehouse", "{dep} slow response {slow_dep_ms}ms")],
        "upstream_error": [("warehouse", "{dep} returned status 502")],
        "cb_open": [], "cb_half": [], "cb_closed": [],
        "health_ok": [("health", "health probe ok")],
        "health_fail": [("health", "health probe failed: timeout")],
        "health_fail_db": [("health", "health probe failed: db ping: context deadline exceeded")],
        "boot": [("main", "inventory-service {ver} starting, GOMAXPROCS={procs}")],
    },
    "node": {
        "info": [(5, "http", "{method} {path} {status} {dur}ms", True),
                 (3, "recommender", "served {n_recs} recommendations for user {uid} (model={model})", True),
                 (2, "cache", "feature cache hit ratio {hit_ratio}", False),
                 (1, "db", "loaded user history for {uid} in {qms}ms", True)],
        "linked": [("http", "{method} {path} {status} {dur}ms")],
        "noise_warn": [("recommender", "model {model} returned fewer than 5 candidates for user {uid}, padding with popular items"),
                       ("event-loop", "event loop lag {lag_ms}ms"),
                       ("http", "request aborted by client {method} {path}")],
        "generic_error": [("http", "Unhandled rejection: TypeError: Cannot read properties of undefined (reading 'items')"),
                          ("recommender", "failed to score candidates for user {uid}: model {model} returned NaN scores"),
                          ("cache", "feature cache write failed: ECONNRESET"),
                          ("http", "{method} {path} 500 {dur}ms")],
        "generic_5xx": [("http", "{method} {path} 500 {slow_dur}ms"), ("http", "{method} {path} 503 {slow_dur}ms")],
        "slow_warn": [("http", "slow response {method} {path} {slow_dur}ms")],
        "db_pool_error": [("knex", "KnexTimeoutError: Knex: Timeout acquiring a connection. The pool is probably full. "
                                   "Are you missing a .transacting(trx) call?"),
                          ("db", "Error loading user history for {uid}: timeout acquiring db connection after {pool_timeout_ms}ms"),
                          ("db", "Database connection timeout")],
        "db_generic_error": [("recommender", "failed to build recommendations for {uid}: upstream data unavailable"),
                             ("http", "{method} {path} 503 {slow_dur}ms")],
        "db_pool_warn": [("db", "pool pending acquires={waiting} used={active}/{pool}")],
        "pool_stats": [("db", "pool status used={active}/{pool} free={idle} pending={waiting}")],
        "memory_warn": [("v8", "Mark-Compact {heap_before} ({heap_max_mb}) -> {heap_after} ({heap_max_mb}) MB, {full_gc_ms} ms: "
                               "allocation failure"),
                        ("monitor", "heap used {heap_mb}MB of {heap_max_mb}MB"),
                        ("event-loop", "event loop lag {gc_ms}ms")],
        "memory_error": [("http", "{method} {path} 500 {slow_dur}ms"),
                         ("recommender", "RangeError: Array buffer allocation failed")],
        "oom_fatal": [("v8", "FATAL ERROR: Reached heap limit Allocation failed - JavaScript heap out of memory")],
        "mem_stats": [("monitor", "process memory rss={rss_mb}MB heapUsed={heap_mb}MB external={ext_mb}MB")],
        "timeout_error": [], "retry_warn": [], "upstream_error": [],
        "cb_open": [], "cb_half": [], "cb_closed": [],
        "health_ok": [("health", "GET /healthz 200")],
        "health_fail": [("health", "GET /healthz 503")],
        "health_fail_db": [("health", "GET /healthz 503 (db: timeout)")],
        "boot": [("pm2", "App [recommendation-service:{pm_id}] online")],
    },
    "postgres": {
        "info": [(3, "postgres", "connection authorized: user={db_user} database=shop application_name={app}", False),
                 (1, "postgres", "disconnection: session time: 0:{sess} user={db_user} database=shop", False),
                 (1, "postgres", "duration: {pg_ms} ms  statement: {stmt}", False)],
        "linked": [],
        "noise_warn": [("postgres", "could not receive data from client: Connection reset by peer"),
                       ("postgres", "duration: {pg_slow_ms} ms  statement: {stmt}")],
        "generic_error": [("postgres", 'duplicate key value violates unique constraint "payments_idempotency_key"'),
                          ("postgres", "canceling autovacuum task")],
        "generic_5xx": [("postgres", "canceling statement due to user request")],
        "slow_statement": [("postgres", "duration: {pg_slow_ms} ms  statement: {stmt}")],
        "lock_wait": [("postgres", "process {pgpid} still waiting for ShareLock on transaction {txid} after 1000.{ms3} ms")],
        "db_error": [("postgres", "canceling statement due to statement timeout"),
                     ("postgres", "canceling statement due to lock timeout")],
        "idle_tx": [("postgres", "terminating connection due to idle-in-transaction timeout")],
        "checkpoint": [("postgres", "checkpoint complete: wrote {buffers} buffers ({buf_pct}%); 0 WAL file(s) added, "
                                    "0 removed, 1 recycled; write={ckpt_s} s")],
        "autovacuum": [("postgres", 'automatic vacuum of table "shop.public.{tbl}": index scans: 1, '
                                    "tuples: {dead} removed, {live} remain")],
    },
}
EVENTS = {
    "deploy_start": ("INFO", "deploy", "rolling update started: {svc} {from_ver} -> {to_ver} ({replicas} replicas)"),
    "deploy_done": ("INFO", "deploy", "rolling update complete: {svc} {to_ver} ({replicas}/{replicas} ready)"),
    "rollout_restart": ("INFO", "k8s.events", "deployment {svc} restarted (rollout restart requested by {user})"),
    "config_reload": ("INFO", "config", "configuration reloaded (revision {rev}, {n_changed} keys changed)"),
    "config_detail": ("INFO", "config", "{detail}"),
    "oom_kill": ("ERROR", "k8s.events", "Container {svc} in pod {host} was OOMKilled (exit code 137), restarting"),
    "oom_kill_alt": ("ERROR", "k8s.events", "pod {host} container {svc} terminated: reason=OOMKilled exitCode=137 "
                                            "restartCount={restarts}"),
    "backoff": ("WARN", "k8s.events", "Back-off restarting failed container {svc} in pod {host}"),
    "flag": ("INFO", "flags", "feature flag '{flag}' set to {flag_pct}% rollout"),
    "hpa": ("INFO", "k8s.events", "HorizontalPodAutoscaler {svc}: scaled from {from_n} to {to_n} replicas (cpu above target 70%)"),
    "cron_start": ("INFO", "scheduler", "job {job} started"),
    "cron_done": ("INFO", "scheduler", "job {job} finished in {job_s}s"),
    "db_hiccup_warn": ("WARN", "app.db", "slow database response ({slow_q_ms}ms) on {tbl}"),
    "db_hiccup_error": ("ERROR", "app.db", "Database connection timeout"),
}
FLAGS = ("checkout_v2", "recs_two_tower", "async_capture", "cart_prefetch", "new_tax_engine")
CRON_JOBS = {"payment-api": "nightly-settlement-export", "recommendation-service": "refresh-item-embeddings",
             "inventory-service": "stock-reconciliation", "orders-api": "abandoned-cart-reminders"}


def _hex(r, n):
    return "".join(r.choice("0123456789abcdef") for _ in range(n))


def _render_path(r, path):
    return (path.replace("{id}", str(r.randint(10000, 999999)))
                .replace("{sku}", f"SKU-{r.randint(10000, 99999)}")
                .replace("{uid}", str(r.randint(100000, 999999))))


def _route(r, c):
    if "_route" not in c:
        routes = ROUTES.get(c["svc"], ROUTES["api-gateway"])
        dep = c.get("dep")
        if dep and c["svc"] == "api-gateway":
            routes = [x for x in routes if x[2] == dep] or routes
        method, path, upstream = r.choice(routes)
        c["_route"] = (method, _render_path(r, path), upstream or c["svc"])
    return c["_route"]


FIELDS = {
    "order_id": lambda r, c: f"ord_{r.randint(100000, 999999)}",
    "pay_id": lambda r, c: f"pay_{_hex(r, 10)}",
    "sku": lambda r, c: f"SKU-{r.randint(10000, 99999)}",
    "uid": lambda r, c: str(r.randint(100000, 999999)),
    "qty": lambda r, c: r.randint(1, 5),
    "items": lambda r, c: r.randint(1, 7),
    "amount": lambda r, c: f"{r.uniform(4, 480):.2f}",
    "currency": lambda r, c: r.choice(("USD", "EUR", "GBP", "USD", "EUR")),
    "rows": lambda r, c: r.randint(0, 40),
    "avail": lambda r, c: r.randint(0, 900),
    "qms": lambda r, c: f"{max(0.3, c['db_lat'] * r.uniform(0.25, 1.1)):.1f}",
    "dur": lambda r, c: max(1, int(c["lat"] * r.uniform(0.15, 0.85))),
    "slow_dur": lambda r, c: max(1, int(c["lat"] * r.uniform(0.85, 1.5))),
    "status": lambda r, c: r.choice((200, 200, 200, 201)),
    "method": lambda r, c: _route(r, c)[0],
    "path": lambda r, c: _route(r, c)[1],
    "upstream": lambda r, c: _route(r, c)[2],
    "upstream_any": lambda r, c: r.choice(("orders-api", "payment-api", "recommendation-service")),
    "healthy": lambda r, c: r.randint(2, 4),
    "host_ip": lambda r, c: f"10.4.{r.randint(0, 15)}.{r.randint(2, 250)}",
    "ip": lambda r, c: f"{r.choice((34, 52, 81, 91, 185))}.{r.randint(0, 255)}.{r.randint(0, 255)}.{r.randint(1, 254)}",
    "client": lambda r, c: r.choice(("mobile-ios", "mobile-android", "web-spa", "partner-acme", "partner-globex")),
    "attempt": lambda r, c: r.randint(1, 3),
    "hex8": lambda r, c: _hex(r, 8),
    "tbl": lambda r, c: r.choice(TABLES.get(c["svc"], ALL_TABLES)),
    "slow_q_ms": lambda r, c: r.randint(250, 900),
    "miss_pct": lambda r, c: r.randint(16, 28),
    "jwt_s": lambda r, c: r.randint(20, 120),
    "gen": lambda r, c: r.choice((0, 1, 2)),
    "gc_ms": lambda r, c: max(3, int(c["gc_base"] * (1 + 12 * c["pressure"] ** 2) * r.uniform(0.6, 1.4))),
    "gc_s": lambda r, c: c["gc_ms"] / 1000.0,
    "full_gc_ms": lambda r, c: int(r.uniform(250, 600) * (1 + 4 * c["pressure"])),
    "heap_before": lambda r, c: c["heap_mb"],
    "heap_after": lambda r, c: int(c["heap_mb"] * (1 - r.uniform(0.04, 0.3) * (1 - 0.85 * c["pressure"]))),
    "n_objects": lambda r, c: r.randint(2000, 90000),
    "merchant": lambda r, c: r.randint(1000, 9999),
    "fraud": lambda r, c: r.randint(71, 95),
    "leap": lambda r, c: f"{r.randint(1, 2)}m{r.randint(0, 59)}s",
    "sync_lag": lambda r, c: r.randint(31, 120),
    "n_recs": lambda r, c: r.randint(8, 24),
    "model": lambda r, c: r.choice(("als-v7", "two-tower-v3", "popularity-v2")),
    "lag_ms": lambda r, c: r.randint(40, 180),
    "hit_ratio": lambda r, c: f"{r.uniform(0.82, 0.97):.2f}",
    "db_user": lambda r, c: r.choice(("orders_rw", "payments_rw", "inventory_rw", "recs_ro")),
    "app": lambda r, c: r.choice(DB_CLIENTS),
    "pg_ms": lambda r, c: f"{r.uniform(250, 600):.3f}",
    "pg_slow_ms": lambda r, c: f"{max(250.0, c['lat_ratio'] * r.uniform(300, 1200)):.3f}",
    "stmt": lambda r, c: r.choice(STATEMENTS),
    "sess": lambda r, c: f"{r.randint(0, 59):02d}:{r.randint(0, 59):02d}.{r.randint(100, 999)}",
    "pgpid": lambda r, c: r.randint(2000, 65000),
    "txid": lambda r, c: r.randint(4_000_000, 9_000_000),
    "ms3": lambda r, c: f"{r.randint(0, 999):03d}",
    "buffers": lambda r, c: r.randint(200, 9000),
    "buf_pct": lambda r, c: f"{r.uniform(0.1, 5.0):.1f}",
    "ckpt_s": lambda r, c: f"{r.uniform(20, 270):.3f}",
    "dead": lambda r, c: r.randint(100, 50000),
    "live": lambda r, c: r.randint(100000, 5000000),
    "backoff_ms": lambda r, c: r.choice((100, 200, 400, 800)),
    "boot_s": lambda r, c: r.uniform(6, 24),
    "procs": lambda r, c: r.choice((2, 4)),
    "pm_id": lambda r, c: r.randint(0, 3),
    "pid": lambda r, c: r.randint(20, 400),
    "threads": lambda r, c: r.randint(8, 40),
    "fds": lambda r, c: r.randint(40, 300),
    "goroutines": lambda r, c: int(r.uniform(150, 260) * (1 + 1.5 * c["pressure"])),
    "next_gc_mb": lambda r, c: int(c["heap_mb"] * r.uniform(1.6, 2.0)),
    "sys_mb": lambda r, c: int(c["heap_mb"] * r.uniform(1.15, 1.35)),
    "num_gc": lambda r, c: r.randint(200, 9000),
    "rss_mb": lambda r, c: int(c["heap_mb"] * r.uniform(1.02, 1.12)),
    "ext_mb": lambda r, c: r.randint(20, 90),
    "elapsed_ms": lambda r, c: c["timeout_ms"] + r.randint(1, 60),
    "slow_dep_ms": lambda r, c: int(c["timeout_ms"] * r.uniform(0.45, 0.95)),
    "budget_ms": lambda r, c: int(c["timeout_ms"] * 0.5),
    "wait_ms": lambda r, c: max(40, int(c["pool_timeout_ms"] * r.uniform(0.05, 0.7) * max(c["pool_sat"], 0.1))),
    "wait_count": lambda r, c: int(c["pool_sat"] * r.uniform(50, 4000)),
    "rev": lambda r, c: r.randint(1200, 4800),
    "n_changed": lambda r, c: r.randint(1, 6),
    "user": lambda r, c: r.choice(("oncall-bot", "j.doe", "s.kim", "a.okafor")),
    "flag": lambda r, c: r.choice(FLAGS),
    "flag_pct": lambda r, c: r.choice((5, 10, 25, 50, 100)),
    "job_s": lambda r, c: r.randint(40, 1100),
}


class Ctx(dict):
    """Template context that generates missing placeholder values on demand."""

    def __init__(self, rng, base):
        super().__init__(base)
        self.rng = rng

    def __missing__(self, key):
        value = FIELDS[key](self.rng, self)
        self[key] = value
        return value


# --------------------------------------------------------------------------- helpers

def clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def smoothstep(x):
    x = clamp(x)
    return x * x * (3 - 2 * x)


def envelope(t, rise_start, rise_end, fall_start, fall_end, linear=False):
    """0 before rise_start, ramps to 1 by rise_end, holds, decays to 0 by fall_end."""
    if t < rise_start or t >= fall_end:
        return 0.0
    if t < rise_end:
        x = (t - rise_start) / max(rise_end - rise_start, 1e-9)
        return clamp(x) if linear else smoothstep(x)
    if t < fall_start:
        return 1.0
    return 1.0 - smoothstep((t - fall_start) / max(fall_end - fall_start, 1e-9))


def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 30:
        return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def balanced(rng, options, n):
    """n items drawn so every option is used as evenly as possible, in random order."""
    out = []
    while len(out) < n:
        block = list(options)
        rng.shuffle(block)
        out.extend(block)
    return out[:n]


def version(rng):
    return f"v{rng.randint(1, 4)}.{rng.randint(0, 30)}.{rng.randint(0, 12)}"


def bump_version(rng, ver):
    major, minor, patch = (int(x) for x in ver[1:].split("."))
    if rng.random() < 0.6:
        return f"v{major}.{minor}.{patch + 1}"
    return f"v{major}.{minor + 1}.0"


def fmt_ms(ms):
    return f"{ms / 1000:.1f}s" if ms >= 1000 else f"{ms:.0f}ms"


def callers_of(svc):
    return [c for c, deps in CALLS.items() if svc in deps]


def reporting_service(case, root):
    """Usually the faulty service itself; sometimes a caller that surfaces the symptoms first."""
    visible = [c for c in callers_of(root) if (c, root) not in case.fallback]
    if visible and case.rng.random() < 0.2:
        return case.rng.choice(visible)
    return root


# --------------------------------------------------------------------------- case planning

SEVERITY_MIX = ("LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "HIGH", "CRITICAL", "CRITICAL")
TARGET_ERR = {"LOW": (1.2, 2.8), "MEDIUM": (3.5, 8.0), "HIGH": (9.0, 22.0), "CRITICAL": (26.0, 48.0)}
TIMEOUT_REACH = {"LOW": (0.7, 1.05), "MEDIUM": (0.9, 1.6), "HIGH": (1.2, 2.5), "CRITICAL": (1.8, 3.5)}
# Fraction of requests that time out when a callee is slower than the caller's timeout.
CASCADE = {"LOW": (0.08, 0.18), "MEDIUM": (0.15, 0.3), "HIGH": (0.3, 0.55), "CRITICAL": (0.55, 0.85)}
# Connection wait (as a fraction of the pool acquisition timeout) at full saturation.
POOL_WAIT = {"LOW": (0.08, 0.2), "MEDIUM": (0.15, 0.35), "HIGH": (0.3, 0.7), "CRITICAL": (0.6, 1.0)}
DB_VARIANTS = ("connection_leak", "slow_query", "traffic_surge", "pool_misconfig")
MEM_VARIANTS = ("unbounded_cache", "session_retention", "library_regression", "listener_leak")
DOWNSTREAM_TARGETS = (
    ("payment-api", "acquirer-gateway", "provider_degraded"),
    ("inventory-service", "warehouse-api", "provider_degraded"),
    ("orders-api", "inventory-service", "dependency_slow"),
    ("orders-api", "inventory-service", "network_latency"),
    ("api-gateway", "recommendation-service", "dependency_overloaded"),
    ("orders-api", "payment-api", "dependency_slow"),
)
NORMAL_KINDS = ("latency_blip", "traffic_spike", "deploy_restart", "dependency_blip",
                "slow_query_burst", "gc_pause_burst")
# Minutes of data before start_time, drawn from the same range for every scenario so the
# window layout does not reveal the scenario.
PRE_ALERT_MINUTES = (60, 130)


def plan_specs(seed, per_scenario, n_normal):
    rng = random.Random(seed)
    specs = []
    for scenario in FAILURE_SCENARIOS:
        severities = balanced(rng, SEVERITY_MIX, per_scenario)
        if scenario == DOWNSTREAM:
            targets = balanced(rng, DOWNSTREAM_TARGETS, per_scenario)
        else:
            services = balanced(rng, DB_CLIENTS, per_scenario)
            variants = balanced(rng, DB_VARIANTS if scenario == DB_POOL else MEM_VARIANTS, per_scenario)
            targets = list(zip(services, [None] * per_scenario, variants))
        for (svc, dep, variant), sev in zip(targets, severities):
            specs.append({"scenario": scenario, "target": svc, "dep": dep, "variant": variant, "severity": sev})
    for kind in balanced(rng, NORMAL_KINDS, n_normal):
        specs.append({"scenario": NORMAL, "target": None, "dep": None, "variant": kind, "severity": "LOW"})

    # Shuffle so incident IDs do not reveal the scenario, then lay cases out chronologically.
    rng.shuffle(specs)
    day = DATASET_START
    hour_weights = [1, 1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 6, 6, 6, 6, 5, 5, 4, 3, 3, 2, 2, 1]
    for idx, spec in enumerate(specs, 1):
        day += timedelta(days=rng.choice((1, 1, 2, 2, 3, 4)))
        hour = rng.choices(range(24), weights=hour_weights)[0]
        spec["incident_id"] = f"INC-{idx:03d}"
        spec["window_start"] = day.replace(hour=hour, minute=rng.randint(0, 59))
        spec["case_seed"] = rng.randrange(1 << 30)
    return specs


def draw_environment(case):
    r = case.rng
    U = r.uniform
    volume = U(0.75, 1.35)  # global request volume for this case
    case.volume = volume
    case.base = {}
    for svc, cfg in SERVICES.items():
        case.base[svc] = NS(
            cpu=U(*cfg["cpu"]), mem=U(*cfg["mem"]), rps=U(*cfg["rps"]) * volume, lat=U(*cfg["lat"]),
            err=U(0.01, 0.08) if svc == "database" else U(0.05, 0.5),
            db=U(*cfg["db"]) * (0.85 + 0.15 * volume) if cfg["db"] else None,
            ds=U(*cfg["ds"]) if cfg["ds"] else None,
        )
    case.shares = {c: {d: U(*rng_) for d, rng_ in deps.items()} for c, deps in CALLS.items()}
    case.timeouts = {k: r.choice(v) for k, v in CALL_TIMEOUTS_MS.items()}
    case.fallback = {("api-gateway", "recommendation-service"): U(0.8, 0.95)}
    case.ext = {s: NS(name=n, share=U(*sh), timeout=r.choice(to)) for s, (n, sh, to) in EXTERNAL_DEPS.items()}
    case.pools = {}
    for svc in DB_CLIENTS:
        sizes, timeouts = POOL_OPTIONS[SERVICES[svc]["stack"]]
        case.pools[svc] = NS(size=r.choice(sizes), overflow=r.choice((0, 5, 10)), timeout_ms=r.choice(timeouts),
                             resize_at=None, new_size=None)
    case.mem_limit = {svc: r.choice(MEMORY_LIMIT_MB[cfg["stack"]]) for svc, cfg in SERVICES.items()}
    case.gc_base = {svc: U(8, 35) for svc in SERVICES}
    case.hosts = {}
    for svc in SERVICES:
        if svc == "database":
            case.hosts[svc] = ["pg-primary-0"]
        else:
            rs = _hex(r, 9)
            case.hosts[svc] = [f"{svc}-{rs}-{_hex(r, 5)}" for _ in range(r.randint(2, 4))]
    case.versions = {svc: version(r) for svc in SERVICES}
    case.verbosity = {svc: U(0.7, 1.3) for svc in SERVICES}
    case.noise_warn = {svc: U(0.03, 0.15) for svc in SERVICES}
    case.slo = {svc: max(50, int(round(case.base[svc].lat * 2.5 / 50.0)) * 50) for svc in SERVICES}
    case.offsets = {svc: r.randint(0, 4) for svc in SERVICES}
    case.traffic = NS(amp=U(0.03, 0.12), period=U(50, 160), phase=U(0, 2 * math.pi))
    case.tf_scale = U(0.35, 0.8)
    case.subsets = {}


def add_deploy(case, t, svc, from_ver=None, to_ver=None):
    r = case.rng
    from_ver = from_ver or case.versions[svc]
    to_ver = to_ver or bump_version(r, from_ver)
    data = {"from_ver": from_ver, "to_ver": to_ver}
    case.events.append((t, svc, "deploy_start", data))
    case.events.append((t + r.uniform(1.5, 4.0), svc, "deploy_done", data))
    case.versions[svc] = to_ver
    return from_ver, to_ver


def add_blip(case, kind, svc, start, length, **kw):
    r = case.rng
    b = NS(kind=kind, svc=svc, start=start, end=start + length, rise=min(1.0, length / 3), **kw)
    if kind == "latency_blip":
        b.mag = kw.get("mag", r.uniform(1.6, 3.0))
        b.err = r.uniform(0.0, 0.4)
    elif kind == "traffic_spike":
        b.mag = kw.get("mag", r.uniform(1.25, 1.7))
        b.cpu = r.uniform(4, 12)
        b.db = r.uniform(8, 22)
    elif kind == "deploy_restart":
        b.err = r.uniform(0.2, 1.2)
        b.mem_drop = case.base[svc].mem * r.uniform(0.08, 0.2)
        b.warm = r.uniform(20, 45)
        add_deploy(case, start - r.uniform(0.3, 1.0), svc)
    elif kind == "dependency_blip":
        b.mag = r.uniform(2.0, 4.0)
        b.retry = r.uniform(0.8, 2.0)
    elif kind == "slow_query_burst":
        b.mag = r.uniform(2.0, 4.5)
    elif kind == "gc_pause_burst":
        b.mag = r.uniform(1.4, 2.2)
        b.mem = r.uniform(3, 7)
    case.blips.append(b)
    return b


def plan_db_pool(case, spec):
    r, U = case.rng, case.rng.uniform
    X, v, sev = spec["target"], spec["variant"], spec["severity"]
    ramp = {"connection_leak": U(12, 28), "slow_query": U(3, 8),
            "traffic_surge": U(4, 10), "pool_misconfig": U(1, 3)}[v]
    start = case.pre_alert
    fault = start - ramp * U(0.6, 0.9) - U(1, 4)
    end = start + U(12, 55)
    rec_end = end + U(3, 10)
    case.W = int(math.ceil(rec_end + U(15, 35)))
    case.fault, case.start, case.end = fault, start, end
    case.root_service = X
    pool = case.pools[X]
    case.tf_scale = U(*CASCADE[sev])
    p = NS(fault=fault, ramp_end=fault + ramp, end=end, rec_end=rec_end, linear=(v == "connection_leak"),
           peak_util=U(96, 100), wait_ms=pool.timeout_ms * U(*POOL_WAIT[sev]), peak_err=U(*TARGET_ERR[sev]),
           cpu_bump=U(0, 14), mem_bump=U(0, 3), retry_boost=U(0, 0.15), specific_ratio=U(0.45, 0.85),
           db_conn=0.0, db_cpu=0.0, db_lat=0.0, db_rps=0.0, other_lat=0.0, other_db=0.0, surge=1.0)
    if v == "connection_leak":
        p.db_conn = U(10, 25)
        p.from_ver, p.to_ver = add_deploy(case, fault - U(2, 8), X)
    elif v == "slow_query":
        p.db_conn, p.db_cpu, p.db_lat = U(15, 30), U(20, 45), U(4, 15)
        p.other_lat, p.other_db = U(0.2, 0.6), U(5, 15)
        p.tbl = r.choice(TABLES[X])
        if r.random() < 0.5:
            p.from_ver, p.to_ver = add_deploy(case, fault - U(1, 10), X)
    elif v == "traffic_surge":
        p.surge = U(1.6, 2.6)
        p.db_conn, p.db_cpu, p.db_rps = U(10, 20), U(10, 25), U(0.3, 0.8)
        n = len(case.hosts[X])
        case.events.append((fault + U(2, 6), X, "hpa", {"from_n": n, "to_n": n + r.randint(1, 3)}))
    elif v == "pool_misconfig":
        old = pool.size
        new = max(3, int(old / U(2.5, 4.5)))
        pool.resize_at, pool.new_size = fault - U(0, 1.5), new
        p.old_pool, p.new_pool = old, new
        p.db_conn = -U(5, 15)
        case.events.append((pool.resize_at, X, "config_reload", {}))
        if r.random() < 0.5:
            key = {"java": "spring.datasource.hikari.maximum-pool-size", "python": "DB_POOL_SIZE",
                   "go": "db.max_open_conns", "node": "knex.pool.max"}[SERVICES[X]["stack"]]
            case.events.append((pool.resize_at + 0.01, X, "config_detail", {"detail": f"config key {key} changed: {old} -> {new}"}))
    case.p = p
    case.apply = apply_db_pool
    case.service = reporting_service(case, X)


def plan_memory_leak(case, spec):
    r, U = case.rng, case.rng.uniform
    X, v, sev = spec["target"], spec["variant"], spec["severity"]
    start = case.pre_alert
    lag = U(1, 5)
    to_symptom = U(35, max(35.0, min(110.0, start - lag - 20)))
    fault = start - lag - to_symptom
    end = start + U(15, 60)
    case.W = int(math.ceil(end + U(2, 6) + U(15, 30)))
    case.fault, case.start, case.end = fault, start, end
    case.root_service = X
    accel = 0.0 if v in ("unbounded_cache", "library_regression") else U(1.0, 3.0)
    symptom_mem = U(78, 84)
    target = symptom_mem - case.base[X].mem
    case.tf_scale = U(*CASCADE[sev])
    peak_err = U(*TARGET_ERR[sev])
    p = NS(fault=fault, end=end, accel=accel, L1=to_symptom, r0=target / (to_symptom + accel * to_symptom / 2),
           oom=r.random() < 0.65, oom_at=U(97, 99.5), plateau=U(96.5, 99.2), restart_len=U(1, 2.5),
           restart_err=peak_err * U(0.6, 1.2), lat_k=U(1.5, 6), gc_cpu=U(5, 25), err_mem=U(84, 90), peak_err=peak_err,
           specific_ratio=U(0.4, 0.8), fresh=U(0.85, 0.97), origin=fault, restart_until=-1.0, restarts=[],
           mitigation="rollback" if v in ("library_regression", "listener_leak") else r.choice(("restart", "hotfix")))
    if v in ("library_regression", "listener_leak"):
        p.from_ver, p.to_ver = add_deploy(case, fault - U(0, 5), X)
    if v == "listener_leak" and r.random() < 0.5:
        case.events.append((fault - U(0, 3), X, "flag", {}))
    if p.mitigation == "rollback":
        case.events.append((end - 0.5, X, "deploy_start", {"from_ver": p.to_ver, "to_ver": p.from_ver}))
        case.events.append((end + U(1.5, 3), X, "deploy_done", {"from_ver": p.to_ver, "to_ver": p.from_ver}))
    elif p.mitigation == "restart":
        case.events.append((end - 0.3, X, "rollout_restart", {}))
    else:
        p.hotfix_ver = bump_version(r, case.versions[X])
        case.events.append((end - 0.5, X, "deploy_start", {"from_ver": case.versions[X], "to_ver": p.hotfix_ver}))
        case.events.append((end + U(1.5, 3), X, "deploy_done", {"from_ver": case.versions[X], "to_ver": p.hotfix_ver}))
    case.p = p
    case.apply = apply_memory_leak
    case.service = reporting_service(case, X)


def plan_downstream(case, spec):
    r, U = case.rng, case.rng.uniform
    X, D, v, sev = spec["target"], spec["dep"], spec["variant"], spec["severity"]
    abrupt = r.random() < 0.5
    ramp = U(0.5, 2) if abrupt else U(4, 12)
    start = case.pre_alert
    fault = start - ramp * U(0.4, 0.9) - U(1, 3)
    end = start + U(8, 50)
    rec_end = end + U(2, 8)
    case.W = int(math.ceil(rec_end + U(15, 35)))
    case.fault, case.start, case.end = fault, start, end
    case.root_service, case.service = D, X
    direct = v in ("provider_degraded", "network_latency")
    ext = case.ext.get(X)
    if ext is not None and ext.name == D:
        timeout, share, base_obs = ext.timeout, ext.share, case.base[X].ds
    else:
        timeout, share, base_obs = case.timeouts[(X, D)], case.shares[X][D], case.base[D].lat
    reach = U(*TIMEOUT_REACH[sev])
    case.tf_scale = U(*CASCADE[sev])
    p = NS(fault=fault, ramp_end=fault + ramp, end=end, rec_end=rec_end, abrupt=abrupt, direct=direct,
           timeout=timeout, share=share, base_obs=base_obs, mult=timeout * reach / base_obs,
           intermittent=r.random() < 0.3, period=U(4, 9), duty=U(0.5, 0.75), low=U(0.1, 0.35),
           retry_absorb=U(0.1, 0.5), cpu_shift=U(-5, 4), mem_shift=U(0, 3), client_retry=U(0, 0.2),
           hold_db=X in DB_CLIENTS and r.random() < 0.45, hold_to=U(55, 80),
           d_cpu=U(35, 55) if v == "dependency_overloaded" else U(-3, 8), d_load=U(0.4, 1.1), d_err=U(0.5, 3))
    target_err = U(*TARGET_ERR[sev])
    p.tf_peak = clamp(target_err / (share * 100 * (1 - p.retry_absorb)), 0.05, 0.9)
    if r.random() < 0.25:
        add_deploy(case, fault - U(3, 20), X)  # unrelated deployment shortly before: a red herring
    if v == "dependency_overloaded" and D in CRON_JOBS:
        job_t = fault - U(0.5, 3)
        case.events.append((job_t, D, "cron_start", {"job": CRON_JOBS[D]}))
        case.events.append((end + U(0, 3), D, "cron_done", {"job": CRON_JOBS[D]}))
    case.p = p
    case.apply = apply_downstream


def plan_normal(case, spec):
    r, U = case.rng, case.rng.uniform
    kind = spec["variant"]
    svc = {"latency_blip": r.choice(("orders-api", "payment-api", "api-gateway", "recommendation-service")),
           "traffic_spike": r.choice(DB_CLIENTS),
           "deploy_restart": r.choice(DB_CLIENTS),
           "dependency_blip": r.choice(("payment-api", "inventory-service")),
           "slow_query_burst": "database",
           "gc_pause_burst": r.choice(("payment-api", "recommendation-service"))}[kind]
    length = U(6, 15) if kind == "traffic_spike" else U(1.5, 4) if kind == "deploy_restart" else U(2, 6)
    case.start = case.pre_alert
    b_start = case.start - U(0.5, 2)
    add_blip(case, kind, svc, b_start, length)
    case.fault = None
    # The alert stays open until on-call acknowledges it, so the window outlasts the blip.
    case.end = b_start + length + U(3, 30)
    case.W = int(math.ceil(case.end + U(15, 35)))
    case.root_service = None
    case.service = r.choice(DB_CLIENTS) if svc == "database" else svc
    case.p = NS(kind=kind, blip_service=svc)
    case.apply = None
    if kind == "traffic_spike" and r.random() < 0.5:
        n = len(case.hosts[svc])
        case.events.append((b_start + U(1, 3), svc, "hpa", {"from_n": n, "to_n": n + 1}))


def add_noise_events(case):
    r, U = case.rng, case.rng.uniform
    others = [s for s in DB_CLIENTS if s not in (case.root_service, case.service)]
    for _ in range(r.randint(0 if case.scenario == NORMAL else 1, 2)):
        kind = r.choice(("latency_blip", "gc_pause_burst", "traffic_spike", "latency_blip"))
        pool = [s for s in others if s in ("payment-api", "recommendation-service")] if kind == "gc_pause_burst" else others + ["api-gateway"]
        if not pool:
            continue
        svc = r.choice(pool)
        add_blip(case, kind, svc, U(3, case.W - 10), U(1.5, 5), mag=U(1.3, 1.9) if kind != "traffic_spike" else U(1.1, 1.35))
    if r.random() < 0.35 and others:
        add_blip(case, "deploy_restart", r.choice(others), U(5, case.W - 10), U(1.5, 3))
    if r.random() < 0.3:
        case.events.append((U(1, case.W - 2), r.choice(DB_CLIENTS), "flag", {}))
    if r.random() < 0.4:
        svc = r.choice(list(CRON_JOBS))
        t = U(1, case.W - 25)
        case.events.append((t, svc, "cron_start", {"job": CRON_JOBS[svc]}))
        case.events.append((t + U(3, 20), svc, "cron_done", {"job": CRON_JOBS[svc]}))
    if r.random() < 0.35:
        svc = r.choice(DB_CLIENTS)
        t = U(2, case.W - 2)
        case.events.append((t, svc, "db_hiccup_warn", {}))
        if r.random() < 0.6:
            case.events.append((t + 0.02, svc, "db_hiccup_error", {}))


def build_case(spec):
    case = NS(incident_id=spec["incident_id"], scenario=spec["scenario"], variant=spec["variant"],
              severity_target=spec["severity"], window_start=spec["window_start"],
              rng=random.Random(spec["case_seed"]), events=[], blips=[])
    draw_environment(case)
    case.pre_alert = case.rng.uniform(*PRE_ALERT_MINUTES)
    case.initial_versions = dict(case.versions)
    {DB_POOL: plan_db_pool, MEMORY_LEAK: plan_memory_leak,
     DOWNSTREAM: plan_downstream, NORMAL: plan_normal}[case.scenario](case, spec)
    add_noise_events(case)
    return case


# --------------------------------------------------------------------------- metric simulation

def apply_blips(case, svc, t, row, comps, sst):
    r = case.rng
    for b in case.blips:
        if b.kind == "deploy_restart" and b.svc == svc and t >= b.start:
            row["mem"] -= b.mem_drop * max(0.0, 1 - (t - b.start) / b.warm)
        affected = b.svc == svc or (b.kind == "slow_query_burst" and svc in DB_CLIENTS)
        if not affected:
            continue
        e = envelope(t, b.start, b.start + b.rise, b.end - b.rise, b.end)
        if e <= 0:
            continue
        if b.kind == "latency_blip":
            row["lat"] *= 1 + (b.mag - 1) * e
            comps["base"] += b.err * e
        elif b.kind == "traffic_spike":
            row["rps"] *= 1 + (b.mag - 1) * e
            row["cpu"] += b.cpu * e
            if row["db"] is not None:
                row["db"] += b.db * e
        elif b.kind == "deploy_restart":
            comps["deploy"] = comps.get("deploy", 0.0) + b.err * e
            row["lat"] *= 1 + 0.3 * e
        elif b.kind == "dependency_blip" and row["ds"] is not None:
            extra = row["ds"] * (b.mag - 1) * e
            row["ds"] += extra
            row["lat"] += extra * 0.5
            sst["retry_noise"] = b.retry * e
            sst["retry_dep"] = case.ext[svc].name if svc in case.ext else None
        elif b.kind == "slow_query_burst":
            if svc == "database":
                row["lat"] *= 1 + (b.mag - 1) * e
                row["cpu"] += 8 * e
            else:
                row["lat"] *= 1 + r.uniform(0.1, 0.2) * e
        elif b.kind == "gc_pause_burst":
            row["lat"] *= 1 + (b.mag - 1) * e
            row["mem"] += b.mem * e
            row["cpu"] += 5 * e
            sst["gc_noise"] = e


def apply_db_pool(case, svc, t, row, comps, sst):
    p, X, r = case.p, case.root_service, case.rng
    e = envelope(t, p.fault, p.ramp_end, p.end, p.rec_end, linear=p.linear)
    if e <= 0:
        return
    v = case.variant
    if v == "traffic_surge" and svc in (X, "api-gateway"):
        share = 1.0 if svc == X else case.shares["api-gateway"].get(X, 0.4)
        row["rps"] *= 1 + (p.surge - 1) * e * share
    if svc == X:
        row["db"] = min(100.0, row["db"] + (p.peak_util - row["db"]) * e + r.uniform(-1.5, 0.5) * e)
        sat = clamp((row["db"] - 85) / max(p.peak_util - 85, 1.0)) ** 1.3
        row["lat"] += p.wait_ms * sat * r.uniform(0.85, 1.15)
        comps["db_pool"] = p.peak_err * sat ** 1.5 * r.uniform(0.8, 1.2)
        row["cpu"] += p.cpu_bump * e + (8 * e if v == "traffic_surge" else 0)
        row["mem"] += p.mem_bump * e
        row["rps"] *= 1 + p.retry_boost * sat
        sst["pool_sat"] = sat
    elif svc == "database":
        row["db"] += p.db_conn * e
        row["cpu"] += p.db_cpu * e
        row["lat"] *= 1 + p.db_lat * e
        row["rps"] *= 1 + p.db_rps * e
        if v == "slow_query":
            comps["stmt_timeout"] = r.uniform(0.2, 1.5) * e
            sst["lock_wait"] = e
        if v == "connection_leak":
            sst["idle_tx"] = e
    elif svc in DB_CLIENTS and v == "slow_query":
        row["lat"] *= 1 + p.other_lat * e
        row["db"] += p.other_db * e


def apply_memory_leak(case, svc, t, row, comps, sst):
    p, X, r = case.p, case.root_service, case.rng
    if svc != X or t < p.fault:
        return
    base_mem = case.base[X].mem
    if t >= p.end:
        # mitigated (rollback / restart / hotfix): fresh processes, memory warms back up
        row["mem"] -= base_mem * (1 - p.fresh) * max(0.0, 1 - (t - p.end) / 30)
        if t - p.end < 2:
            comps["restart"] = r.uniform(0.3, 1.5)
        return
    if t < p.restart_until:
        sst["restarting"] = True
        row["mem"] = base_mem * p.fresh + r.uniform(-0.5, 0.5)
        row["rps"] *= r.uniform(0.45, 0.75)
        row["lat"] *= r.uniform(1.6, 3.0)
        comps["restart"] = p.restart_err * r.uniform(0.7, 1.3)
        return
    tau = max(0.0, t - p.origin)
    mem = row["mem"] + p.r0 * (tau + p.accel * tau * tau / (2 * p.L1))
    if p.oom and mem >= p.oom_at and p.end - t > 2:
        p.restarts.append(t)
        p.restart_until = t + p.restart_len
        p.origin = p.restart_until
        sst["oom_kill"] = True
        mem = min(mem, 99.6)
    elif p.oom:
        mem = min(mem, 99.6)
    else:
        mem = min(mem, p.plateau + r.uniform(-0.6, 0.4))
    row["mem"] = mem
    pressure = clamp((mem - 70) / 28)
    row["lat"] *= 1 + p.lat_k * pressure ** 2
    row["cpu"] += p.gc_cpu * pressure ** 1.5
    comps["memory"] = p.peak_err * clamp((mem - p.err_mem) / (99 - p.err_mem)) ** 1.5 * r.uniform(0.8, 1.2)
    sst["mem_pressure"] = pressure


def apply_downstream(case, svc, t, row, comps, sst):
    p, X, D, r = case.p, case.service, case.root_service, case.rng
    e = envelope(t, p.fault, p.ramp_end, p.end, p.rec_end, linear=not p.abrupt)
    if p.intermittent and e > 0 and ((t - p.fault) % p.period) / p.period > p.duty:
        e *= p.low
    if e <= 0:
        return
    if svc == X:
        if p.direct:
            observed = p.base_obs * (1 + (p.mult - 1) * e)
            capped = min(observed, p.timeout * r.uniform(1.0, 1.04))
            inc = max(0.0, capped - p.base_obs)
            row["ds"] += inc * min(1.0, p.share * 1.6)
            row["lat"] += inc * min(1.0, p.share * 1.3)
            tf = p.tf_peak * clamp((observed - 0.6 * p.timeout) / (0.6 * p.timeout))
            comps[("timeout", D)] = tf * p.share * 100 * (1 - p.retry_absorb) * r.uniform(0.85, 1.15)
            sst["tf"][D] = tf
            sst["fr"][D] = tf
        row["cpu"] += p.cpu_shift * e
        row["mem"] += p.mem_shift * e
        if p.hold_db and row["db"] is not None:
            row["db"] += max(0.0, p.hold_to - row["db"]) * e
        row["rps"] *= 1 + p.client_retry * e
    elif svc == D and not p.direct:
        row["lat"] *= 1 + (p.mult - 1) * e
        row["cpu"] += p.d_cpu * e
        if case.variant == "dependency_overloaded":
            row["rps"] *= 1 + p.d_load * e
            comps["overload"] = p.d_err * e


def propagate(case, svc, row, comps, sst, lat_delta, err_delta):
    for dep, w in case.shares.get(svc, {}).items():
        dl, de = max(0.0, lat_delta.get(dep, 0.0)), max(0.0, err_delta.get(dep, 0.0))
        if dl < 1 and de < 0.05:
            continue
        timeout, fb = case.timeouts[(svc, dep)], case.fallback.get((svc, dep), 0.0)
        base_d = case.base[dep].lat
        observed = base_d + dl
        inc = max(0.0, min(observed, timeout) - base_d)
        row["ds"] += inc * min(1.0, 2 * w)
        row["lat"] += inc * min(1.0, 1.5 * w) * (1 - 0.8 * fb)
        tf = clamp((observed - 0.7 * timeout) / (0.6 * timeout)) * case.tf_scale
        if tf > 0:
            comps[("timeout", dep)] = comps.get(("timeout", dep), 0.0) + tf * w * 100 * (1 - fb)
        if de > 0:
            comps[("upstream_error", dep)] = comps.get(("upstream_error", dep), 0.0) + de * w * (1 - fb) * 0.9
        sst["tf"][dep] = max(sst["tf"].get(dep, 0.0), tf)
        sst["fr"][dep] = min(1.0, tf + de / 100)
        if fb > 0:
            sst["fallback"][dep] = (tf * 100 + de) * w


def simulate(case):
    r = case.rng
    noise = {svc: {} for svc in SERVICES}

    def ar(svc, key, sigma, rho=0.7):
        x = rho * noise[svc].get(key, 0.0) + r.gauss(0, sigma)
        noise[svc][key] = x
        return x

    walk = 0.0
    states = []
    for m in range(case.W):
        t = float(m)
        walk = 0.8 * walk + r.gauss(0, 0.012)
        tr = case.traffic
        traffic = 1 + tr.amp * math.sin(2 * math.pi * t / tr.period + tr.phase) + walk
        minute, lat_delta, err_delta = {}, {}, {}
        for svc in SERVICE_ORDER:
            b = case.base[svc]
            row = {
                "cpu": b.cpu * (0.75 + 0.25 * traffic) + ar(svc, "cpu", 1.2),
                "mem": b.mem + ar(svc, "mem", 0.35),
                "rps": b.rps * traffic * (1 + ar(svc, "rps", 0.03)),
                "lat": b.lat * (1 + 0.25 * (traffic - 1)) * math.exp(ar(svc, "lat", 0.06)),
                "db": b.db * (0.85 + 0.15 * traffic) + ar(svc, "db", 1.5) if b.db is not None else None,
                "ds": b.ds * math.exp(ar(svc, "ds", 0.07)) if b.ds is not None else None,
            }
            comps = {"base": max(0.0, b.err * (1 + ar(svc, "err", 0.3)))}
            sst = {"restarting": False, "oom_kill": False, "pool_sat": 0.0, "mem_pressure": 0.0, "tf": {}, "fr": {},
                   "fallback": {}, "retry_noise": 0.0, "retry_dep": None, "gc_noise": 0.0, "lock_wait": 0.0, "idle_tx": 0.0}
            if r.random() < 0.012:  # isolated one-minute outliers
                row["lat"] *= r.uniform(1.4, 2.6)
                comps["base"] += r.uniform(0.1, 0.6)
            lat_before = row["lat"]
            apply_blips(case, svc, t, row, comps, sst)
            if case.apply:
                case.apply(case, svc, t, row, comps, sst)
            propagate(case, svc, row, comps, sst, lat_delta, err_delta)
            lat_delta[svc] = row["lat"] - lat_before
            err_delta[svc] = sum(v for k, v in comps.items() if k != "base")
            row["error_rate"] = min(100.0, sum(comps.values()))
            row["cpu"] = clamp(row["cpu"], 1.0, 99.5)
            row["mem"] = clamp(row["mem"], 1.0, 99.6)
            row["rps"] = max(0.0, row["rps"])
            row["lat"] = max(0.5, row["lat"])
            if row["db"] is not None:
                row["db"] = clamp(row["db"], 0.0, 100.0)
            minute[svc] = (row, comps, sst)
        states.append(minute)
    return states


# --------------------------------------------------------------------------- log generation

SUBSET_CATEGORIES = {"db_pool_error", "db_generic_error", "db_pool_warn", "memory_error", "memory_warn",
                     "timeout_error", "retry_warn", "upstream_error", "generic_5xx", "slow_warn"}
ERROR_CATEGORY = {"base": "generic_error", "deploy": "generic_5xx", "restart": "generic_5xx",
                  "overload": "generic_5xx", "stmt_timeout": "db_error"}


def templates(case, svc, category):
    """Templates for a category; failure categories use an incident-specific subset."""
    stack = SERVICES[svc]["stack"]
    options = BANK[stack].get(category, [])
    if category not in SUBSET_CATEGORIES or len(options) <= 1:
        return options
    key = (stack, category)
    if key not in case.subsets:
        k = max(1, round(len(options) * case.rng.uniform(0.5, 1.0)))
        case.subsets[key] = case.rng.sample(options, k)
    return case.subsets[key]


def pool_size(case, svc, t):
    pool = case.pools[svc]
    if pool.resize_at is not None and t >= pool.resize_at and t < case.end + 3:
        return pool.new_size
    return pool.size


def minute_context(case, svc, m, row, sst, minute):
    heap_max = case.mem_limit[svc]
    c = {"svc": svc, "lat": max(1, int(row["lat"])), "slo_ms": case.slo[svc], "ver": case.versions[svc],
         "db_lat": minute["database"][0]["lat"], "mem_pct": int(round(row["mem"])),
         "pressure": clamp((row["mem"] - 70) / 28), "gc_base": case.gc_base[svc],
         "heap_mb": int(row["mem"] / 100 * heap_max), "heap_max_mb": heap_max, "soft_mb": int(heap_max * 0.85),
         "lat_ratio": row["lat"] / case.base[svc].lat, "pool_sat": sst["pool_sat"],
         "replicas": len(case.hosts[svc])}
    if svc in case.pools:
        pool = case.pools[svc]
        size = pool_size(case, svc, m)
        active = min(size, int(round(row["db"] / 100 * size)))
        waiting = int(sst["pool_sat"] * case.rng.uniform(4, 45)) if sst["pool_sat"] > 0.05 else 0
        c.update(pool=size, overflow=pool.overflow, active=active, idle=size - active, waiting=waiting,
                 pool_timeout_ms=pool.timeout_ms, pool_timeout_s=pool.timeout_ms / 1000.0)
    return c


def dep_fields(case, svc, dep, rng, fr=0.0):
    method, path, action = DEP_CALLS[dep]
    timeout = case.timeouts.get((svc, dep)) or case.ext[svc].timeout
    return {"dep": dep, "dep_method": method, "dep_path": _render_path(rng, path), "dep_action": action,
            "timeout_ms": timeout, "timeout_s": timeout / 1000.0, "fr": int(round(min(1.0, fr) * 100))}


def generate_logs(case, states):
    r = case.rng
    iid, t0 = case.incident_id, case.window_start
    t_end = t0 + timedelta(minutes=case.W)
    logs = []
    events = sorted(case.events, key=lambda e: e[0])
    restarts = list(getattr(case.p, "restarts", []) or [])
    for i, t_r in enumerate(restarts, 1):
        X = case.root_service
        t_r += r.uniform(0.05, 0.6)
        events.append((t_r, X, "oom_fatal", {}))
        events.append((t_r + r.uniform(0.01, 0.08), X, "oom_kill" if r.random() < 0.5 else "oom_kill_alt", {"restarts": i}))
        if i > 1 and r.random() < 0.6:
            events.append((t_r + r.uniform(0.1, 0.3), X, "backoff", {}))
        events.append((t_r + case.p.restart_len, X, "boot", {}))
    events.sort(key=lambda e: e[0])
    by_minute = {}
    for ev in events:
        if 0 <= ev[0] < case.W:
            by_minute.setdefault(int(ev[0]), []).append(ev)
    cb_state = {}

    def emit(ts, svc, level, logger, msg, trace=None, host=None):
        ts = min(max(ts, t0), t_end - timedelta(milliseconds=1))
        logs.append({"timestamp": ts, "service": svc, "host": host or r.choice(case.hosts[svc]), "level": level,
                     "logger": logger, "message": msg, "trace_id": trace, "incident_id": iid})

    def at(m, lo=0.0, hi=60.0):
        return t0 + timedelta(minutes=m, seconds=r.uniform(lo, hi))

    def emit_from(category, svc, level, ctx_base, m, extra=None, trace=None, ts=None, host=None):
        options = templates(case, svc, category)
        if not options:
            return None
        logger, fmt = r.choice(options)
        ctx = Ctx(r, ctx_base)
        if extra:
            ctx.update(extra)
        ts = ts or at(m)
        emit(ts, svc, level, logger, fmt.format_map(ctx), trace, host)
        return ts

    for m in range(case.W):
        minute = states[m]
        err_traces = {}
        ctxs = {}
        for svc in SERVICE_ORDER:
            row, comps, sst = minute[svc]
            stack = SERVICES[svc]["stack"]
            bank = BANK[stack]
            base_ctx = minute_context(case, svc, m, row, sst, minute)
            ctxs[svc] = base_ctx
            cfg_mid = sum(SERVICES[svc]["rps"]) / 2
            restarting = sst["restarting"]

            # normal request / background activity, proportional to request volume
            lam = SERVICES[svc]["logs_per_min"] * row["rps"] / cfg_mid * case.verbosity[svc] * (0.25 if restarting else 1)
            weights = [w for w, *_ in bank["info"]]
            for _ in range(poisson(r, lam)):
                _, logger, fmt, traced = r.choices(bank["info"], weights=weights)[0]
                ctx = Ctx(r, base_ctx)
                ts = at(m)
                trace = _hex(r, 16) if traced else None
                emit(ts, svc, "INFO", logger, fmt.format_map(ctx), trace)
                upstream = ctx.get("_route", (None, None, None))[2]
                if svc == "api-gateway" and upstream in ctxs and r.random() < 0.2 and BANK[SERVICES[upstream]["stack"]]["linked"]:
                    lg, lf = r.choice(BANK[SERVICES[upstream]["stack"]]["linked"])
                    uctx = Ctx(r, ctxs[upstream])
                    emit(ts - timedelta(milliseconds=r.randint(2, 40)), upstream, "INFO", lg, lf.format_map(uctx), trace)

            # background warnings unrelated to any incident
            for _ in range(poisson(r, case.noise_warn[svc])):
                emit_from("noise_warn", svc, "WARN", base_ctx, m, trace=_hex(r, 16) if r.random() < 0.5 else None)

            # slow requests
            ratio = row["lat"] / case.base[svc].lat
            for _ in range(poisson(r, clamp(ratio - 1.8, 0, 6) * 0.6)):
                emit_from("slow_warn", svc, "WARN", base_ctx, m, trace=_hex(r, 16))

            # errors, sampled from the per-minute error composition
            total = sum(comps.values())
            lam_err = min(12.0, row["rps"] / cfg_mid * total * 0.3)
            keys = list(comps)
            cweights = [comps[k] for k in keys]
            for _ in range(poisson(r, lam_err) if total > 0 else 0):
                key = r.choices(keys, weights=cweights)[0]
                extra, trace, ts = None, _hex(r, 16), None
                if isinstance(key, tuple):
                    kind, dep = key
                    category = "timeout_error" if kind == "timeout" else "upstream_error"
                    extra = dep_fields(case, svc, dep, r, sst["fr"].get(dep, 0.0))
                    if dep in err_traces and err_traces[dep] and r.random() < 0.6:
                        dep_ts, trace = r.choice(err_traces[dep])
                        ts = dep_ts + timedelta(milliseconds=r.randint(3, 250))
                    if not templates(case, svc, category):
                        category = "generic_5xx"
                elif key == "db_pool":
                    category = "db_pool_error" if r.random() < case.p.specific_ratio else "db_generic_error"
                elif key == "memory":
                    category = "memory_error" if row["mem"] >= 94 and r.random() < case.p.specific_ratio else "generic_5xx"
                else:
                    category = ERROR_CATEGORY.get(key, "generic_error")
                ts = emit_from(category, svc, "ERROR", base_ctx, m, extra, trace, ts)
                if ts is not None:
                    err_traces.setdefault(svc, []).append((ts, trace))

            # scenario-driven warnings
            if sst["pool_sat"] > 0.02:
                for _ in range(poisson(r, 2.5 * sst["pool_sat"])):
                    emit_from("db_pool_warn", svc, "WARN", base_ctx, m, trace=_hex(r, 16))
            pressure = sst["mem_pressure"] + 0.25 * sst["gc_noise"]
            if pressure > 0.02:
                for _ in range(poisson(r, 3.0 * pressure ** 1.3)):
                    emit_from("memory_warn", svc, "WARN", base_ctx, m)
            for dep, tf in sst["tf"].items():
                for _ in range(poisson(r, 5.0 * tf)):
                    emit_from("retry_warn", svc, "WARN", base_ctx, m, dep_fields(case, svc, dep, r), _hex(r, 16))
            if sst["retry_noise"] > 0 and sst["retry_dep"]:
                for _ in range(poisson(r, sst["retry_noise"])):
                    emit_from("retry_warn", svc, "WARN", base_ctx, m, dep_fields(case, svc, sst["retry_dep"], r), _hex(r, 16))
            for dep, vol in sst["fallback"].items():
                for _ in range(poisson(r, min(8.0, vol * 0.4))):
                    emit_from("fallback_warn", svc, "WARN", base_ctx, m, {"dep": dep}, _hex(r, 16))
            if svc == "database":
                for _ in range(poisson(r, clamp(ratio - 1.5, 0, 8) * 0.8)):
                    emit_from("slow_statement", svc, "WARN", base_ctx, m)
                for _ in range(poisson(r, 1.2 * sst["lock_wait"])):
                    emit_from("lock_wait", svc, "WARN", base_ctx, m)
                for _ in range(poisson(r, 0.5 * sst["idle_tx"])):
                    emit_from("idle_tx", svc, "WARN", base_ctx, m)

            # circuit breakers on outbound dependencies
            if bank.get("cb_open"):
                for dep, fr in sst["fr"].items():
                    state = cb_state.get((svc, dep), "CLOSED")
                    extra = dep_fields(case, svc, dep, r, fr)
                    if state == "CLOSED" and fr >= 0.5:
                        emit_from("cb_open", svc, "WARN", base_ctx, m, extra)
                        cb_state[(svc, dep)] = "OPEN"
                    elif state == "OPEN":
                        emit_from("cb_half", svc, "INFO", base_ctx, m, extra)
                        cb_state[(svc, dep)] = "HALF_OPEN"
                    elif state == "HALF_OPEN":
                        if fr >= 0.5:
                            emit_from("cb_open", svc, "WARN", base_ctx, m, extra)
                            cb_state[(svc, dep)] = "OPEN"
                        elif fr < 0.2:
                            emit_from("cb_closed", svc, "INFO", base_ctx, m, extra)
                            cb_state[(svc, dep)] = "CLOSED"
                for (c_svc, dep), state in list(cb_state.items()):
                    if c_svc == svc and dep not in sst["fr"] and state != "CLOSED":
                        emit_from("cb_closed", svc, "INFO", base_ctx, m, dep_fields(case, svc, dep, r))
                        cb_state[(svc, dep)] = "CLOSED"

            # periodic health checks, pool and memory stats
            tick = (m + case.offsets[svc]) % 5 == 0
            if tick and svc == "api-gateway":
                upstreams = list(case.shares["api-gateway"])
                worst = max(upstreams, key=lambda u: minute[u][0]["error_rate"])
                w_row, _, w_sst = minute[worst]
                if w_row["error_rate"] > 20 or w_sst["restarting"]:
                    emit_from("health_fail", svc, "WARN", base_ctx, m, {"dep": worst})
                else:
                    emit_from("health_ok", svc, "INFO", base_ctx, m)
            elif tick and svc != "database":
                failing = (restarting or total > 20 or (sst["pool_sat"] > 0.85 and r.random() < 0.7)
                           or (sst["mem_pressure"] > 0.9 and r.random() < 0.5))
                if failing:
                    cat = "health_fail_db" if sst["pool_sat"] > 0.5 and bank.get("health_fail_db") else "health_fail"
                    emit_from(cat, svc, "WARN", base_ctx, m)
                else:
                    emit_from("health_ok", svc, "INFO", base_ctx, m)
            if tick and svc in case.pools:
                emit_from("pool_stats", svc, "WARN" if base_ctx["waiting"] > 0 else "INFO", base_ctx, m)
            if svc not in ("api-gateway", "database") and not restarting:
                period = 3 if stack == "java" else 5
                if (m + case.offsets[svc]) % period == 1:
                    emit_from("mem_stats", svc, "INFO", base_ctx, m)
            if svc == "database":
                if tick:
                    emit_from("checkpoint", svc, "INFO", base_ctx, m)
                if r.random() < 0.08:
                    emit_from("autovacuum", svc, "INFO", base_ctx, m)

        # discrete events (deployments, config changes, restarts, jobs, ...)
        for t_ev, svc, kind, data in by_minute.get(m, []):
            ts = t0 + timedelta(minutes=t_ev)
            host = r.choice(case.hosts[svc])
            ctx = Ctx(r, {**ctxs[svc], **data, "svc": svc, "host": host})
            if kind in ("oom_fatal", "boot"):
                options = BANK[SERVICES[svc]["stack"]][kind]
                logger, fmt = r.choice(options)
                emit(ts, svc, "ERROR" if kind == "oom_fatal" else "INFO", logger, fmt.format_map(ctx), host=host)
                continue
            level, logger, fmt = EVENTS[kind]
            emit(ts, svc, level, logger, fmt.format_map(ctx), _hex(r, 16) if kind.startswith("db_hiccup") else None, host)
            if kind in ("deploy_done", "rollout_restart") and BANK[SERVICES[svc]["stack"]].get("boot"):
                logger, fmt = r.choice(BANK[SERVICES[svc]["stack"]]["boot"])
                emit(ts - timedelta(seconds=r.uniform(5, 40)), svc, "INFO", logger, fmt.format_map(ctx), host=host)

    logs.sort(key=lambda rec: rec["timestamp"])
    for rec in logs:
        rec["timestamp"] = rec["timestamp"].isoformat(timespec="milliseconds")
    return logs


# --------------------------------------------------------------------------- metadata

USER_SYMPTOM = {
    "orders-api": "failed or very slow checkouts",
    "payment-api": "card payments failing or stuck in pending",
    "inventory-service": "items showing as unavailable and slow cart updates",
    "recommendation-service": "missing or slow product recommendations on the home page",
    "api-gateway": "slow page loads and intermittent 5xx errors",
}
FEATURE = {"orders-api": "checkout", "payment-api": "payments", "inventory-service": "stock availability",
           "recommendation-service": "recommendations", "api-gateway": "storefront API"}
SOURCES = ("PagerDuty alert", "Synthetic monitor", "Customer support escalation", "SLO burn-rate alert", "On-call report")


def series(states, svc, key, lo, hi):
    lo, hi = max(0, int(lo)), min(len(states), int(math.ceil(hi)) + 1)
    return [states[m][svc][0][key] for m in range(lo, hi) if states[m][svc][0][key] is not None]


def service_stats(case, states):
    ref = case.fault if case.fault is not None else case.start
    pre = (max(0, ref - 30), ref - 1)
    stats = {}
    for svc in SERVICES:
        s = NS()
        for key in ("lat", "error_rate", "db", "mem", "ds", "cpu", "rps"):
            before = series(states, svc, key, *pre)
            during = series(states, svc, key, case.start, case.end)
            setattr(s, f"pre_{key}", statistics.median(before) if before else None)
            setattr(s, f"peak_{key}", max(during) if during else None)
        stats[svc] = s
    return stats


def affected(case, stats):
    out = []
    for svc in [case.service] + [s for s in SERVICE_ORDER if s != case.service]:
        s = stats[svc]
        if (s.peak_error_rate - s.pre_error_rate >= 1.0
                or (s.peak_lat >= 2 * s.pre_lat and s.peak_lat - s.pre_lat > 50)):
            out.append(svc)
    for svc in (case.root_service, case.service):
        if svc in SERVICES and svc not in out:
            out.insert(0 if svc == case.service else len(out), svc)
    return out


def severity_of(case, stats):
    duration = case.end - case.start
    candidates = [case.service, "api-gateway"] + ([case.root_service] if case.root_service in SERVICES else [])
    peak_err = max(stats[s].peak_error_rate - stats[s].pre_error_rate for s in candidates)
    lat_ratio = stats[case.service].peak_lat / stats[case.service].pre_lat
    if peak_err >= 25 or (peak_err >= 15 and duration >= 40):
        return "CRITICAL"
    if peak_err >= 8 or (peak_err >= 5 and duration >= 45):
        return "HIGH"
    if peak_err >= 2.5 or lat_ratio >= 6:
        return "MEDIUM"
    return "LOW"


def root_cause_text(case):
    p, X, D, v = case.p, case.root_service, case.root_service, case.variant
    if case.scenario == DB_POOL:
        pool = case.pools[X]
        detail = {
            "connection_leak": (f"An error path introduced in {X} {getattr(p, 'to_ver', '')} did not return connections "
                                f"to the pool; the pool (max {pool.size}) saturated gradually and requests queued "
                                "until the acquisition timeout.",
                                f"Rolled back {X} to {getattr(p, 'from_ver', '')}, fixed the missing connection release "
                                "and enabled pool leak detection."),
            "slow_query": (f"A slow query on table {getattr(p, 'tbl', 'orders')} (missing index plus lock contention) held "
                           f"connections for seconds, saturating the {X} connection pool (max {pool.size}).",
                           "Terminated the long-running queries, added the missing index and set a statement_timeout "
                           "for the offending query."),
            "traffic_surge": (f"A traffic surge (~{p.surge:.1f}x normal) exceeded the capacity of the {X} connection "
                              f"pool (max {pool.size}); requests waited for connections until timeout.",
                              f"Scaled out {X}, raised the pool size within the database max_connections budget and "
                              "added rate limiting for campaign traffic."),
            "pool_misconfig": (f"A configuration change reduced the {X} connection pool from {getattr(p, 'old_pool', '')} "
                               f"to {getattr(p, 'new_pool', '')} connections; normal traffic exhausted the pool.",
                               "Reverted the pool size configuration and added validation for datasource settings."),
        }[v]
    elif case.scenario == MEMORY_LEAK:
        ver = getattr(p, "to_ver", case.initial_versions[X])
        detail = {
            "unbounded_cache": (f"An in-process cache in {X} had no eviction policy or TTL and grew without bound.",
                                "Restarted the pods to restore service and added a max size and TTL to the cache."),
            "session_retention": (f"Per-request session objects in {X} were retained by a global registry, so memory "
                                  "grew with traffic.",
                                  "Restarted the pods, removed the global registry reference and added a heap usage alert."),
            "library_regression": (f"A dependency upgrade shipped in {X} {ver} leaked buffers on every request.",
                                   f"Rolled back {X} to {getattr(p, 'from_ver', '')} and pinned the library version."),
            "listener_leak": (f"Event listeners registered per request in {X} {ver} were never removed.",
                              f"Rolled back {X} to {getattr(p, 'from_ver', '')} and fixed listener deregistration."),
        }[v]
        if p.mitigation == "hotfix":
            detail = (detail[0], f"Deployed hotfix {p.hotfix_ver} for {X} that bounds the leaking structure.")
    elif case.scenario == DOWNSTREAM:
        X = case.service
        detail = {
            "provider_degraded": (f"External dependency {D} degraded and responded slowly; {X} calls exceeded the "
                                  f"{p.timeout}ms client timeout.",
                                  f"Failed over to the secondary {D} region and tuned the {X} timeout and retry budget."),
            "dependency_slow": (f"{D} responded slowly (CPU throttling on its node pool), so {X} calls timed out at "
                                f"{p.timeout}ms.",
                                f"Moved {D} pods off the degraded node pool and tuned the {X} circuit breaker."),
            "network_latency": (f"Cross-zone network degradation between {X} and {D} pushed call latency beyond the "
                                f"{p.timeout}ms timeout; {D} itself was healthy.",
                                "Routed traffic to same-zone endpoints until the cloud provider fixed the network issue."),
            "dependency_overloaded": (f"{D} was overloaded by a batch job, saturating CPU and slowing responses; "
                                      f"{X} calls timed out.",
                                      f"Paused the batch job, scaled {D} and moved the job to off-peak hours."),
        }[v]
        if p.intermittent:
            detail = (detail[0] + " The degradation was intermittent (flapping).", detail[1])
    else:
        detail = (f"No underlying fault: benign {p.kind.replace('_', ' ')} on {p.blip_service}.",
                  "No action required; the alert auto-resolved.")
    return detail


def expected_symptoms(case, stats):
    s, p, X = stats, case.p, case.root_service
    out = []
    if case.scenario == DB_POOL:
        out += [f"{X} db_connection_utilization saturated at ~{s[X].peak_db:.0f}% (baseline ~{s[X].pre_db:.0f}%)",
                f"connection acquisition timeouts and database errors in {X} logs",
                f"{X} p95 latency rises from ~{fmt_ms(s[X].pre_lat)} to ~{fmt_ms(s[X].peak_lat)}",
                f"{X} error rate rises to ~{s[X].peak_error_rate:.1f}%",
                f"{X} memory stays near baseline; CPU at most moderately elevated"]
        if case.variant == "traffic_surge":
            out.append(f"request_rate on {X} rises ~{s[X].peak_rps / s[X].pre_rps:.1f}x before saturation")
        if case.variant == "slow_query":
            out.append("database query latency and CPU elevated; slow statement and lock wait logs")
        if case.variant == "connection_leak":
            out.append(f"utilization climbs gradually after deployment of {X} {p.to_ver}")
        if case.variant == "pool_misconfig":
            out.append(f"configuration reload on {X} shortly before saturation; database server connections drop")
    elif case.scenario == MEMORY_LEAK:
        mins = int(case.start - case.fault)
        out += [f"{X} memory_usage climbs gradually from ~{s[X].pre_mem:.0f}% to ~{s[X].peak_mem:.0f}% over ~{mins}+ minutes",
                f"increasing GC / heap pressure logs on {X}",
                f"{X} p95 latency rises from ~{fmt_ms(s[X].pre_lat)} to ~{fmt_ms(s[X].peak_lat)} as memory grows",
                f"{X} errors appear late, error rate up to ~{s[X].peak_error_rate:.1f}%",
                f"{X} db_connection_utilization stays within normal range"]
        if p.restarts:
            out.append(f"{len(p.restarts)} OOM kill / restart event(s) with memory drop and error spike")
        if case.variant in ("library_regression", "listener_leak"):
            out.append(f"deployment of {X} {p.to_ver} shortly before memory growth starts")
    elif case.scenario == DOWNSTREAM:
        X, D = case.service, case.root_service
        out += [f"{X} downstream_latency_ms rises from ~{fmt_ms(s[X].pre_ds)} to ~{fmt_ms(s[X].peak_ds)} "
                f"(client timeout {p.timeout}ms)",
                f"timeout and retry logs on calls from {X} to {D}",
                f"{X} p95 latency rises to ~{fmt_ms(s[X].peak_lat)}, error rate up to ~{s[X].peak_error_rate:.1f}%",
                f"{X} CPU and memory stay near baseline"]
        if D in SERVICES and not p.direct:
            if case.variant == "dependency_overloaded":
                out.append(f"{D} CPU near saturation (~{s[D].peak_cpu:.0f}%) and server-side latency elevated")
            else:
                out.append(f"{D} server-side latency elevated while its CPU and memory stay normal")
        if case.variant == "network_latency":
            out.append(f"{D} server-side latency normal while caller-observed latency is high")
        if p.hold_db:
            out.append(f"{X} db_connection_utilization moderately elevated (~{s[X].peak_db:.0f}%) but not saturated")
        if p.intermittent:
            out.append("intermittent / flapping latency pattern")
    return out


def describe(case, stats):
    r, svc = case.rng, case.service
    s = stats[svc]
    src = r.choice(SOURCES)
    if case.scenario == NORMAL:
        what = {"latency_blip": "p95 latency alert", "traffic_spike": "traffic anomaly alert",
                "deploy_restart": "error-rate alert", "dependency_blip": "latency alert",
                "slow_query_burst": "latency alert", "gc_pause_burst": "latency alert"}[case.p.kind]
        minutes = max(1, int(round(case.end - case.start)))
        title = r.choice((f"Transient {what} on {svc}", f"{svc}: {what} auto-resolved"))
        desc = r.choice((
            f"{src}: {what} on {svc} fired for ~{minutes} minutes and auto-resolved. Please confirm whether follow-up is needed.",
            f"{src}: brief {what} on {svc} (p95 up to {fmt_ms(s.peak_lat)}); no customer reports so far.",
        ))
        return title, desc
    err = s.peak_error_rate
    title = r.choice((f"{svc}: elevated latency and errors", f"{svc} error-rate SLO burn",
                      f"Degraded {FEATURE[svc]}", f"Timeouts and 5xx on {svc}"))
    desc = r.choice((
        f"{src}: {svc} p95 latency reached {fmt_ms(s.peak_lat)} (normally ~{fmt_ms(s.pre_lat)}) and error rate peaked at {err:.1f}%.",
        f"Customers report {USER_SYMPTOM[svc]}. {svc} shows elevated latency and intermittent 5xx responses.",
        f"{src}: error budget burn on {svc}; {err:.1f}% of requests failing at peak and some requests timing out.",
        f"Elevated latency on {svc} (p95 {fmt_ms(s.peak_lat)}) with rising errors reported by consumers.",
    ))
    return title, desc


def build_metadata(case, states):
    stats = service_stats(case, states)
    title, desc = describe(case, stats)
    detail, resolution = root_cause_text(case)
    ts = lambda minutes: (case.window_start + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    is_normal = case.scenario == NORMAL
    meta = {
        "incident_id": case.incident_id,
        "title": title,
        "scenario": case.scenario,
        "service": case.service,
        "severity": severity_of(case, stats),
        "start_time": ts(case.start),
        "end_time": ts(case.end),
        "duration_minutes": round(case.end - case.start, 1),
        "window_start": ts(0),
        "window_end": ts(case.W),
        "description": desc,
        "true_root_cause": None if is_normal else case.scenario,
        "root_cause_service": case.root_service,
        "root_cause_variant": None if is_normal else case.variant,
        "root_cause_detail": detail,
        "fault_start_time": None if is_normal else ts(case.fault),
        "expected_symptoms": expected_symptoms(case, stats),
        "affected_services": [] if is_normal else affected(case, stats),
        "resolution": resolution,
        "evidence_files": {"logs": f"logs/{case.incident_id}.jsonl", "metrics": f"metrics/{case.incident_id}.csv"},
    }
    return meta


def metric_rows(case, states):
    out = []
    for m, minute in enumerate(states):
        stamp = (case.window_start + timedelta(minutes=m)).isoformat(timespec="seconds")
        for svc in sorted(SERVICES):
            row = minute[svc][0]
            out.append([stamp, case.incident_id, svc, f"{row['cpu']:.2f}", f"{row['mem']:.2f}", f"{row['rps']:.2f}",
                        f"{row['lat']:.1f}", f"{row['error_rate']:.3f}",
                        "" if row["db"] is None else f"{row['db']:.2f}",
                        "" if row["ds"] is None else f"{row['ds']:.1f}"])
    return out


# --------------------------------------------------------------------------- output

def reset_output(out):
    """Delete only files this generator owns, so unrelated data is never touched."""
    owned = (("raw/incidents", "INC-*.json"), ("raw/logs", "INC-*.jsonl"), ("raw/metrics", "INC-*.csv"))
    for sub, pattern in owned:
        folder = out / sub
        folder.mkdir(parents=True, exist_ok=True)
        for path in folder.glob(pattern):
            path.unlink()
    generated = out / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    for name in GENERATED_FILES:
        (generated / name).unlink(missing_ok=True)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_case(out, meta, logs, rows):
    iid = meta["incident_id"]
    paths = [out / "raw/incidents" / f"{iid}.json", out / "raw/logs" / f"{iid}.jsonl", out / "raw/metrics" / f"{iid}.csv"]
    with paths[0].open("w", encoding="utf-8", newline="\n") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
        f.write("\n")
    with paths[1].open("w", encoding="utf-8", newline="\n") as f:
        for rec in logs:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    with paths[2].open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(METRIC_COLUMNS)
        writer.writerows(rows)
    return paths


def generate(seed, per_scenario, n_normal, out):
    reset_output(out)
    specs = plan_specs(seed, per_scenario, n_normal)
    index, files, level_counts = [], {}, {"INFO": 0, "WARN": 0, "ERROR": 0}
    total_logs = total_rows = 0
    for spec in specs:
        case = build_case(spec)
        states = simulate(case)
        logs = generate_logs(case, states)
        rows = metric_rows(case, states)
        meta = build_metadata(case, states)
        for path in write_case(out, meta, logs, rows):
            files[path.relative_to(out).as_posix()] = sha256(path)
        for rec in logs:
            level_counts[rec["level"]] += 1
        total_logs += len(logs)
        total_rows += len(rows)
        index.append([meta["incident_id"], meta["scenario"], meta["service"], meta["root_cause_service"] or "",
                      meta["severity"], meta["start_time"], meta["end_time"], meta["duration_minutes"],
                      len(logs), len(rows)])

    with (out / "generated/incidents_index.csv").open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, lineterminator="\n")
        writer.writerow(["incident_id", "scenario", "service", "root_cause_service", "severity", "start_time",
                         "end_time", "duration_minutes", "log_records", "metric_rows"])
        writer.writerows(index)
    counts = {s: sum(1 for row in index if row[1] == s) for s in FAILURE_SCENARIOS + (NORMAL,)}
    manifest = {
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "incidents_per_scenario": per_scenario,
        "normal_cases": n_normal,
        "total_cases": len(index),
        "cases_per_scenario": counts,
        "log_records": total_logs,
        "log_levels": level_counts,
        "metric_rows": total_rows,
        "files": dict(sorted(files.items())),
    }
    with (out / "generated/manifest.json").open("w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    return manifest, index


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate the synthetic incident / log / metric dataset.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help=f"random seed (default {DEFAULT_SEED})")
    parser.add_argument("--incidents-per-scenario", type=int, default=10, help="failure incidents per scenario (default 10)")
    parser.add_argument("--normal-cases", type=int, default=5, help="normal / no-failure cases (default 5)")
    parser.add_argument("--output-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                        help="dataset root (default: <repo>/data)")
    parser.add_argument("--skip-validation", action="store_true", help="do not run validate_dataset.py afterwards")
    args = parser.parse_args(argv)
    if args.incidents_per_scenario < 1 or args.normal_cases < 0:
        parser.error("--incidents-per-scenario must be >= 1 and --normal-cases >= 0")

    out = args.output_dir.resolve()
    manifest, index = generate(args.seed, args.incidents_per_scenario, args.normal_cases, out)

    print(f"Generated {manifest['total_cases']} cases into {out} (seed={args.seed})")
    for scenario, n in manifest["cases_per_scenario"].items():
        sev = {}
        for row in index:
            if row[1] == scenario:
                sev[row[4]] = sev.get(row[4], 0) + 1
        sev_txt = ", ".join(f"{k}={sev[k]}" for k in ("LOW", "MEDIUM", "HIGH", "CRITICAL") if k in sev)
        print(f"  {scenario:<31} {n:>3}  ({sev_txt})")
    lv = manifest["log_levels"]
    print(f"  log records: {manifest['log_records']} (INFO={lv['INFO']}, WARN={lv['WARN']}, ERROR={lv['ERROR']})")
    print(f"  metric rows: {manifest['metric_rows']}")

    if args.skip_validation:
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from validate_dataset import validate
    print()
    return 0 if validate(out) else 1


if __name__ == "__main__":
    sys.exit(main())
