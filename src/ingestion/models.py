"""Validated, typed representations of the raw incident dataset.

Two groups of models are kept strictly apart:

* Operational evidence, which the investigation engine may inspect: ``IncidentContext``,
  ``LogEvent``, ``MetricPoint`` and the ``IncidentEvidenceBundle`` that combines them.
* Ground truth, used only for evaluation: ``IncidentGroundTruth`` and the
  ``IncidentEvaluationRecord`` that pairs it with an evidence bundle.

Nothing in the first group references the second.

Timestamps: the dataset stores ISO-8601 timestamps without a UTC offset, and the README
documents them as UTC. The ingestion layer keeps them as naive ``datetime`` values holding
UTC wall-clock time and applies no timezone conversion. Timestamps that carry an offset are
rejected, because comparing naive and aware datetimes raises ``TypeError`` and would break
chronological sorting.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator


def parse_timestamp(value: object) -> datetime:
    """Parse an ISO-8601 string into a naive datetime (UTC wall-clock time)."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            raise ValueError(f"invalid ISO-8601 timestamp {value!r}") from None
    else:
        raise ValueError(f"timestamp must be an ISO-8601 string, got {type(value).__name__}")
    if parsed.tzinfo is not None:
        raise ValueError(f"timestamp {value!r} has a UTC offset; the dataset uses naive UTC timestamps")
    return parsed


Timestamp = Annotated[datetime, BeforeValidator(parse_timestamp)]
IncidentId = Annotated[str, Field(pattern=r"^INC-\d{3,}$")]
NonEmptyStr = Annotated[str, Field(min_length=1)]
Percent = Annotated[float, Field(ge=0, le=100, allow_inf_nan=False)]
NonNegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# --------------------------------------------------------------------------- logs


class LogLevel(StrEnum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"


_LEVEL_ALIASES = {"WARNING": "WARN"}


def normalize_level(value: object) -> str:
    """Normalize case and whitespace and map ``WARNING`` to ``WARN``. Any other level is rejected."""
    if not isinstance(value, str):
        raise ValueError(f"level must be a string, got {type(value).__name__}")
    level = value.strip().upper()
    level = _LEVEL_ALIASES.get(level, level)
    if level not in LogLevel.__members__:
        raise ValueError(f"unknown log level {value!r}; expected one of {', '.join(LogLevel)}")
    return level


class EventType(StrEnum):
    """What a log line reports, derived from its text. It never names a root cause or scenario."""

    # requests handled by the logging service
    REQUEST_STARTED = "request_started"
    REQUEST_COMPLETED = "request_completed"
    REQUEST_CLIENT_ERROR = "request_client_error"
    REQUEST_FAILED = "request_failed"
    SLOW_REQUEST = "slow_request"
    CLIENT_DISCONNECTED = "client_disconnected"
    RATE_LIMITED = "rate_limited"
    REQUEST_VALIDATION_FAILED = "request_validation_failed"
    # health checks
    HEALTH_CHECK_PASSED = "health_check_passed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    # calls to other services
    DOWNSTREAM_TIMEOUT = "downstream_timeout"
    DOWNSTREAM_ERROR = "downstream_error"
    DOWNSTREAM_SLOW = "downstream_slow"
    RETRY = "retry"
    CIRCUIT_BREAKER_STATE_CHANGE = "circuit_breaker_state_change"
    HOST_EJECTED = "host_ejected"
    HOST_RESTORED = "host_restored"
    UPSTREAM_CLUSTER_STATUS = "upstream_cluster_status"
    FALLBACK_RESPONSE = "fallback_response"
    OPERATION_TIMEOUT = "operation_timeout"
    # database access and the database server
    DB_QUERY = "db_query"
    SLOW_DB_QUERY = "slow_db_query"
    DB_TIMEOUT = "db_timeout"
    DB_CONNECTION_ERROR = "db_connection_error"
    DB_CONNECTION_WAIT = "db_connection_wait"
    DB_POOL_STATS = "db_pool_stats"
    DB_ERROR = "db_error"
    DB_LOCK_WAIT = "db_lock_wait"
    DB_STATEMENT_CANCELLED = "db_statement_cancelled"
    DB_CONNECTION_OPENED = "db_connection_opened"
    DB_CONNECTION_CLOSED = "db_connection_closed"
    DB_CONNECTION_TERMINATED = "db_connection_terminated"
    DB_CLIENT_CONNECTION_RESET = "db_client_connection_reset"
    DB_MAINTENANCE = "db_maintenance"
    # runtime and memory
    GC_PAUSE = "gc_pause"
    MEMORY_STATS = "memory_stats"
    MEMORY_PRESSURE = "memory_pressure"
    MEMORY_ALLOCATION_FAILED = "memory_allocation_failed"
    OOM_KILLED = "oom_killed"
    PROCESS_KILLED = "process_killed"
    WORKER_TIMEOUT = "worker_timeout"
    EVENT_LOOP_LAG = "event_loop_lag"
    THREAD_STARVATION = "thread_starvation"
    # caches
    CACHE_HIT = "cache_hit"
    CACHE_MISS = "cache_miss"
    CACHE_STATS = "cache_stats"
    CACHE_ERROR = "cache_error"
    # lifecycle and change events
    DEPLOYMENT_STARTED = "deployment_started"
    DEPLOYMENT_COMPLETED = "deployment_completed"
    SERVICE_STARTED = "service_started"
    SERVICE_RESTART = "service_restart"
    AUTOSCALING = "autoscaling"
    CONFIG_CHANGE = "config_change"
    FEATURE_FLAG_CHANGE = "feature_flag_change"
    SCHEDULED_JOB_STARTED = "scheduled_job_started"
    SCHEDULED_JOB_FINISHED = "scheduled_job_finished"
    # application and business events
    BUSINESS_OPERATION = "business_operation"
    BUSINESS_WARNING = "business_warning"
    BUSINESS_ERROR = "business_error"
    APPLICATION_ERROR = "application_error"
    MESSAGE_PUBLISH_FAILED = "message_publish_failed"
    TLS_ERROR = "tls_error"
    AUTH_TOKEN_EXPIRING = "auth_token_expiring"
    DEPRECATED_API_CALL = "deprecated_api_call"
    UNKNOWN = "unknown"


class LogEvent(_Frozen):
    """One application log record. ``message`` is kept exactly as written."""

    timestamp: Timestamp
    incident_id: IncidentId
    service: NonEmptyStr
    host: NonEmptyStr
    level: Annotated[LogLevel, BeforeValidator(normalize_level)]
    logger: NonEmptyStr
    message: NonEmptyStr
    trace_id: NonEmptyStr | None
    event_type: EventType


# --------------------------------------------------------------------------- metrics

METRIC_FIELDS = ("cpu_usage", "memory_usage", "request_rate", "latency_ms", "error_rate",
                 "db_connection_utilization", "downstream_latency_ms")
# Blank in the CSV when the metric does not apply to a service (api-gateway has no DB pool;
# database and recommendation-service make no downstream calls).
NULLABLE_METRIC_FIELDS = frozenset({"db_connection_utilization", "downstream_latency_ms"})


class MetricPoint(_Frozen):
    """One service's metrics for one minute. ``None`` means the metric does not apply to the service."""

    timestamp: Timestamp
    incident_id: IncidentId
    service: NonEmptyStr
    cpu_usage: Percent
    memory_usage: Percent
    request_rate: NonNegative
    latency_ms: NonNegative
    error_rate: Percent
    db_connection_utilization: Percent | None
    downstream_latency_ms: NonNegative | None


# --------------------------------------------------------------------------- incidents


class Severity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IncidentContext(_Frozen):
    """What on-call sees when the alert fires. It contains no ground truth.

    The raw metadata also has ``expected_symptoms`` and ``affected_services``. They are derived
    from the injected fault and describe its mechanism, which the dataset README classifies as
    ground truth, so they are part of ``IncidentGroundTruth`` instead.
    """

    incident_id: IncidentId
    title: NonEmptyStr
    service: NonEmptyStr
    severity: Severity
    start_time: Timestamp
    end_time: Timestamp
    duration_minutes: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    window_start: Timestamp
    window_end: Timestamp
    description: NonEmptyStr

    @model_validator(mode="after")
    def _check_times(self) -> IncidentContext:
        if not self.window_start <= self.start_time <= self.end_time <= self.window_end:
            raise ValueError("expected window_start <= start_time <= end_time <= window_end")
        return self


Scenario = Literal["DB_CONNECTION_POOL_EXHAUSTION", "MEMORY_LEAK", "DOWNSTREAM_SERVICE_TIMEOUT", "NORMAL"]
RootCause = Literal["DB_CONNECTION_POOL_EXHAUSTION", "MEMORY_LEAK", "DOWNSTREAM_SERVICE_TIMEOUT"]


class IncidentGroundTruth(_Frozen):
    """The answer for one incident. Use it only for evaluation, never as investigation input."""

    incident_id: IncidentId
    scenario: Scenario
    true_root_cause: RootCause | None
    root_cause_service: NonEmptyStr | None
    root_cause_variant: NonEmptyStr | None
    root_cause_detail: NonEmptyStr
    fault_start_time: Timestamp | None
    expected_symptoms: tuple[str, ...]
    affected_services: tuple[str, ...]
    resolution: NonEmptyStr

    @model_validator(mode="after")
    def _check_consistency(self) -> IncidentGroundTruth:
        fault_fields = (self.true_root_cause, self.root_cause_service, self.root_cause_variant, self.fault_start_time)
        if self.scenario == "NORMAL":
            if any(value is not None for value in fault_fields):
                raise ValueError("NORMAL cases must have null true_root_cause, root_cause_service, "
                                 "root_cause_variant and fault_start_time")
        else:
            if self.true_root_cause != self.scenario:
                raise ValueError(f"true_root_cause {self.true_root_cause!r} does not match scenario {self.scenario!r}")
            if any(value is None for value in fault_fields):
                raise ValueError("failure cases need root_cause_service, root_cause_variant and fault_start_time")
        return self


# --------------------------------------------------------------------------- combined objects


class IncidentEvidenceBundle(_Frozen):
    """Everything an investigation may inspect for one incident: context, logs and metrics.

    It has no ground-truth field. Logs are sorted by timestamp; metrics by timestamp, then service.
    """

    context: IncidentContext
    logs: tuple[LogEvent, ...]
    metrics: tuple[MetricPoint, ...]

    @property
    def incident_id(self) -> str:
        return self.context.incident_id

    @model_validator(mode="after")
    def _check_consistency(self) -> IncidentEvidenceBundle:
        iid = self.context.incident_id
        foreign = {r.incident_id for r in (*self.logs, *self.metrics) if r.incident_id != iid}
        if foreign:
            raise ValueError(f"records from other incidents {sorted(foreign)} in bundle for {iid}")
        if any(a.timestamp > b.timestamp for a, b in zip(self.logs, self.logs[1:])):
            raise ValueError("logs must be sorted by timestamp")
        keys = [(m.timestamp, m.service) for m in self.metrics]
        if keys != sorted(keys):
            raise ValueError("metrics must be sorted by timestamp, then service")
        return self


class IncidentEvaluationRecord(_Frozen):
    """An evidence bundle with its ground truth, for scoring an investigation afterwards."""

    evidence: IncidentEvidenceBundle
    ground_truth: IncidentGroundTruth

    @model_validator(mode="after")
    def _check_ids(self) -> IncidentEvaluationRecord:
        if self.evidence.incident_id != self.ground_truth.incident_id:
            raise ValueError(f"evidence is for {self.evidence.incident_id} but ground truth is for "
                             f"{self.ground_truth.incident_id}")
        return self
