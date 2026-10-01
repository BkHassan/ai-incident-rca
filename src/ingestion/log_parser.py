"""Parse per-incident JSON Lines log files into validated ``LogEvent`` objects.

Each line of ``raw/logs/INC-XXX.jsonl`` holds one JSON object with the fields ``timestamp``,
``service``, ``host``, ``level``, ``logger``, ``message``, ``trace_id`` and ``incident_id``.
The parser adds ``event_type``, taken from the message by fixed regular-expression rules.
It describes what the line reports, such as a request or a database timeout, and never
names a root cause.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from .errors import IngestionError, RecordIssue, describe_validation_error
from .models import EventType, LogEvent

E = EventType
_I = re.IGNORECASE

# Access-log lines that carry an HTTP status code: envoy, uvicorn, Node, Spring and the
# key=value styles used by the Python and Go services.
_STATUS_PATTERNS = (
    re.compile(r'^"[A-Z]+ \S+ HTTP/[\d.]+" (?P<status>\d{3}) upstream='),
    re.compile(r'" (?P<status>\d{3}) \(\d+ms\)$'),
    re.compile(r"^GET /recommendations/\S+ (?P<status>\d{3}) \d+ms$"),
    re.compile(r"^Completed [A-Z]+ \S+ (?P<status>\d{3}) in \d+ms$"),
    re.compile(r"^request completed method=\S+ path=\S+ status=(?P<status>\d{3})"),
)
_HEALTHZ = re.compile(r"^GET /healthz (?P<status>\d{3})")

# Ordered rules: the first matching pattern decides the event type.
_RULES: tuple[tuple[EventType, re.Pattern[str]], ...] = tuple((event, re.compile(pattern, flags)) for event, pattern, flags in (
    # health checks come first, because failed probes often mention the database or a timeout
    (E.HEALTH_CHECK_PASSED, r"^health check passed|^health probe ok|^Health check UP", 0),
    (E.HEALTH_CHECK_FAILED, r"health check failed|health probe failed|readiness check failed|"
                            r"^Health check (DOWN|timed out)", 0),
    # lifecycle and change events
    (E.DEPLOYMENT_STARTED, r"^rolling update started", 0),
    (E.DEPLOYMENT_COMPLETED, r"^rolling update complete", 0),
    (E.SERVICE_RESTART, r"rollout restart|^deployment \S+ restarted", 0),
    (E.SERVICE_STARTED, r"starting, GOMAXPROCS|^Booting worker|^Started \w+ in|^App \[.+\] online", 0),
    (E.AUTOSCALING, r"HorizontalPodAutoscaler|scaled from \d+ to \d+ replicas", 0),
    (E.CONFIG_CHANGE, r"^configuration reloaded|^config key ", 0),
    (E.FEATURE_FLAG_CHANGE, r"^feature flag ", 0),
    (E.SCHEDULED_JOB_STARTED, r"^job \S+ started", 0),
    (E.SCHEDULED_JOB_FINISHED, r"^job \S+ finished", 0),
    # runtime and memory; GC traces come before allocation failures because V8 reports
    # "allocation failure" as an ordinary GC trigger
    (E.GC_PAUSE, r"^GC pause|^Pause (Full|Young)|^Mark-Compact|^Scavenge|^gc: collection|GC assist time", 0),
    (E.MEMORY_STATS, r"^memstats |^process stats rss=|^process memory rss=", 0),
    (E.MEMORY_PRESSURE, r"^heap in use|^Heap usage at|^heap used|exceeds soft limit", 0),
    (E.OOM_KILLED, r"OOMKilled", 0),
    (E.PROCESS_KILLED, r"SIGKILL", 0),
    (E.WORKER_TIMEOUT, r"WORKER TIMEOUT", 0),
    (E.MEMORY_ALLOCATION_FAILED, r"OutOfMemoryError|\bMemoryError\b|out of memory|cannot allocate memory|"
                                 r"allocation failed", _I),
    (E.EVENT_LOOP_LAG, r"event loop (lag|blocked)", _I),
    (E.THREAD_STARVATION, r"thread starvation", _I),
    # requests handled by the logging service (status-coded access logs are handled separately)
    (E.REQUEST_STARTED, r"^request started |^Received [A-Z]+ /", 0),
    (E.SLOW_REQUEST, r"^slow request|^slow response |exceeded latency SLO", _I),
    (E.REQUEST_FAILED, r"^request failed |^Request [A-Z]+ \S+ failed with status", 0),
    (E.CLIENT_DISCONNECTED, r"closed connection before response|request aborted by client|"
                            r"^client (canceled request|disconnected before response)", 0),
    (E.RATE_LIMITED, r"rate limit exceeded", _I),
    (E.REQUEST_VALIDATION_FAILED, r"^request validation failed", _I),
    # database connection acquisition
    (E.DB_TIMEOUT, r"database connection timeout|Connection is not available, request timed out|"
                   r"QueuePool limit .* timed out|failed to acquire connection|"
                   r"could not obtain database connection|timeout acquiring (a |db )?connection|"
                   r"TimeoutError acquiring connection|timeout waiting for database connection", _I),
    (E.DB_CONNECTION_ERROR, r"Unable to acquire JDBC Connection|JDBCConnectionException|"
                            r"CannotCreateTransactionException", 0),
    (E.DB_CONNECTION_WAIT, r"waiting for database connection|connection checkout took|"
                           r"Connection acquisition took|connection wait \d+ms exceeded|pool pending acquires", _I),
    (E.DB_POOL_STATS, r"Pool stats \(|^db pool stats |^db stats open=|^pool status used=", 0),
    # retries come before timeouts: "Retry ... after SocketTimeoutException" is a retry
    (E.RETRY, r"\bretry(ing)?\b", _I),
    # calls to other services
    (E.DOWNSTREAM_TIMEOUT, r"did not respond within|ReadTimeout|ConnectTimeout|Read timed out|Client\.Timeout|"
                           r"upstream (request )?timeout|\S+-(api|gateway|service) timeout after|timed out calling", 0),
    (E.DOWNSTREAM_ERROR, r"returned \d{3} Service Unavailable|upstream error \d{3} from|upstream connect error|"
                         r"^upstream reset|server disconnected without sending|upstream data unavailable|"
                         r"malformed response from|from merchant endpoint", 0),
    (E.DOWNSTREAM_SLOW, r"call took \d+ms, exceeding budget|slow upstream response|^upstream \S+ slow|"
                        r"slow response \d+ms|sync lag", 0),
    (E.CIRCUIT_BREAKER_STATE_CHANGE, r"circuit ?breaker", _I),
    (E.HOST_EJECTED, r"^ejecting host", 0),
    (E.HOST_RESTORED, r"returned to cluster \S+ after ejection", 0),
    (E.UPSTREAM_CLUSTER_STATUS, r"^cluster \S+: \d+ healthy hosts", 0),
    (E.FALLBACK_RESPONSE, r"returning cached payload|serving fallback response", 0),
    # database queries and server events
    (E.DB_LOCK_WAIT, r"still waiting for \w+Lock", 0),
    (E.DB_STATEMENT_CANCELLED, r"^canceling statement due to", 0),
    (E.DB_MAINTENANCE, r"^checkpoint complete|^automatic vacuum|autovacuum", 0),
    (E.DB_CONNECTION_OPENED, r"^connection authorized", 0),
    (E.DB_CONNECTION_CLOSED, r"^disconnection: ", 0),
    (E.DB_CONNECTION_TERMINATED, r"^terminating connection due to", 0),
    (E.DB_CLIENT_CONNECTION_RESET, r"could not receive data from client", 0),
    (E.SLOW_DB_QUERY, r"slow database response|^Slow repository call|^slow query table=", 0),
    (E.DB_QUERY, r"^query ok |^database query completed|^Query .+ completed in|^loaded user history|"
                 r"^duration: [\d.]+ ms\s+statement:", 0),
    (E.DB_ERROR, r"duplicate key value|row not found|transaction rolled back|OperationalError|^SQL Error", 0),
    # caches
    (E.CACHE_STATS, r"cache (hit|miss) ratio", _I),
    (E.CACHE_HIT, r"cache hit\b", _I),
    (E.CACHE_MISS, r"cache miss\b", _I),
    (E.CACHE_ERROR, r"cache write failed", _I),
    # business and application events
    (E.BUSINESS_OPERATION, r"^order \S+ created|^stock reservation confirmed|^stock reserved |^stock level read|"
                           r"^Payment \S+ (authorized|captured)|^served \d+ recommendations", 0),
    (E.BUSINESS_WARNING, r"declined by issuer|^Fraud score|expired before confirmation|below reorder threshold|"
                         r"returned fewer than \d+ candidates", 0),
    (E.BUSINESS_ERROR, r"^Refund for payment \S+ rejected", 0),
    (E.MESSAGE_PUBLISH_FAILED, r"^failed to publish ", 0),
    (E.APPLICATION_ERROR, r"^Unhandled (rejection|exception)|NaN scores|internal error", 0),
    (E.TLS_ERROR, r"TLS handshake error", 0),
    (E.AUTH_TOKEN_EXPIRING, r"^token for client \S+ expires", 0),
    (E.DEPRECATED_API_CALL, r"deprecated endpoint", _I),
    # timeouts whose target the message does not name
    (E.OPERATION_TIMEOUT, r"context deadline exceeded|timed out|timeout", _I),
))

_PG_DURATION = re.compile(r"^duration: [\d.]+ ms\s+statement:")


def _status_event(status: int, message: str) -> EventType:
    if status >= 500:
        return E.REQUEST_FAILED
    if status >= 400:
        return E.REQUEST_CLIENT_ERROR
    return E.SLOW_REQUEST if "slow=true" in message else E.REQUEST_COMPLETED


def classify_event(message: str, level: str = "INFO") -> EventType:
    """Return the event type described by a log message.

    The rules only look at the message text. The exception is Postgres statement-duration lines,
    which are identical at INFO and WARN, so ``level`` separates a normal query from a slow one.
    """
    match = _HEALTHZ.match(message)
    if match:
        return E.HEALTH_CHECK_PASSED if match["status"].startswith("2") else E.HEALTH_CHECK_FAILED
    for pattern in _STATUS_PATTERNS:
        match = pattern.search(message)
        if match:
            return _status_event(int(match["status"]), message)
    if _PG_DURATION.match(message):
        return E.SLOW_DB_QUERY if level.strip().upper().startswith("WARN") else E.DB_QUERY
    for event, pattern in _RULES:
        if pattern.search(message):
            return event
    return E.UNKNOWN


def load_logs(path: str | Path, incident_id: str | None = None) -> list[LogEvent]:
    """Load and validate one JSON Lines log file, sorted by timestamp.

    Records with the same timestamp keep their file order. If ``incident_id`` is given, every
    record must belong to it. All problems in the file are collected and raised together as one
    ``IngestionError``. A missing file raises ``OSError``.
    """
    path = Path(path)
    events: list[LogEvent] = []
    issues: list[RecordIssue] = []
    with path.open(encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            location = f"line {line_no}"
            if not line.strip():
                issues.append(RecordIssue(location, "blank line"))
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(RecordIssue(location, f"invalid JSON ({exc.msg} at column {exc.colno})"))
                continue
            if not isinstance(record, dict):
                issues.append(RecordIssue(location, f"expected a JSON object, got {type(record).__name__}"))
                continue
            rid = record.get("incident_id") if isinstance(record.get("incident_id"), str) else None
            if "event_type" in record:
                issues.append(RecordIssue(location, "unexpected field 'event_type' (it is derived by the parser)", rid))
                continue
            message, level = record.get("message"), record.get("level")
            event_type = (classify_event(message, level if isinstance(level, str) else "")
                          if isinstance(message, str) else E.UNKNOWN)
            try:
                event = LogEvent.model_validate({**record, "event_type": event_type})
            except ValidationError as exc:
                issues.append(RecordIssue(location, describe_validation_error(exc), rid))
                continue
            if incident_id is not None and event.incident_id != incident_id:
                issues.append(RecordIssue(location, f"record belongs to {event.incident_id}, expected {incident_id}", rid))
                continue
            events.append(event)
    if not issues and not events:
        issues.append(RecordIssue("file", "contains no log records"))
    if issues:
        raise IngestionError(path, issues, incident_id)
    return sorted(events, key=lambda event: event.timestamp)
