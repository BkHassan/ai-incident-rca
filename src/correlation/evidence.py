"""Relevance rules, evidence IDs, and observational summaries.

A log is relevant because of its own ``event_type`` and ``level``, never because of an
evaluation label. Summaries describe what was recorded; they do not say that one record
produced another.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import datetime

from detection.models import AnomalyPoint, AnomalySeverity, AnomalyWindow
from ingestion.models import EventType, LogEvent, LogLevel

from .models import EvidenceType
from .temporal import near_window

# Lifecycle / change events: keep every occurrence; they are rare and useful as time context.
CHANGE_EVENT_TYPES = frozenset({
    EventType.DEPLOYMENT_STARTED, EventType.DEPLOYMENT_COMPLETED,
    EventType.SERVICE_RESTART, EventType.SERVICE_STARTED,
    EventType.AUTOSCALING, EventType.CONFIG_CHANGE, EventType.FEATURE_FLAG_CHANGE,
    EventType.SCHEDULED_JOB_STARTED, EventType.SCHEDULED_JOB_FINISHED,
})

RARE_EVENT_TYPES = CHANGE_EVENT_TYPES | frozenset({
    EventType.OOM_KILLED, EventType.PROCESS_KILLED, EventType.WORKER_TIMEOUT,
    EventType.MEMORY_ALLOCATION_FAILED, EventType.CIRCUIT_BREAKER_STATE_CHANGE,
    EventType.HOST_EJECTED, EventType.HOST_RESTORED,
})

# High-volume operational signals: keep the first occurrence plus a count through the last.
COLLAPSE_EVENT_TYPES = frozenset({
    EventType.REQUEST_FAILED, EventType.SLOW_REQUEST, EventType.REQUEST_CLIENT_ERROR,
    EventType.DOWNSTREAM_TIMEOUT, EventType.DOWNSTREAM_ERROR, EventType.DOWNSTREAM_SLOW,
    EventType.DB_TIMEOUT, EventType.DB_CONNECTION_ERROR, EventType.DB_CONNECTION_WAIT,
    EventType.DB_ERROR, EventType.DB_LOCK_WAIT, EventType.DB_STATEMENT_CANCELLED,
    EventType.DB_CONNECTION_TERMINATED, EventType.DB_CLIENT_CONNECTION_RESET,
    EventType.OPERATION_TIMEOUT, EventType.RETRY, EventType.FALLBACK_RESPONSE,
    EventType.SLOW_DB_QUERY, EventType.APPLICATION_ERROR, EventType.HEALTH_CHECK_FAILED,
    EventType.MEMORY_PRESSURE, EventType.EVENT_LOOP_LAG, EventType.THREAD_STARVATION,
    EventType.CACHE_ERROR, EventType.MESSAGE_PUBLISH_FAILED, EventType.BUSINESS_ERROR,
    EventType.CLIENT_DISCONNECTED, EventType.RATE_LIMITED,
})

RELEVANT_EVENT_TYPES = RARE_EVENT_TYPES | COLLAPSE_EVENT_TYPES | frozenset({
    EventType.TLS_ERROR, EventType.AUTH_TOKEN_EXPIRING, EventType.DEPRECATED_API_CALL,
})

TIMEOUT_EVENT_TYPES = frozenset({
    EventType.DB_TIMEOUT, EventType.DOWNSTREAM_TIMEOUT, EventType.OPERATION_TIMEOUT, EventType.WORKER_TIMEOUT,
})
ERROR_EVENT_TYPES = frozenset({
    EventType.REQUEST_FAILED, EventType.DOWNSTREAM_ERROR, EventType.DB_ERROR, EventType.DB_CONNECTION_ERROR,
    EventType.APPLICATION_ERROR, EventType.BUSINESS_ERROR, EventType.CACHE_ERROR, EventType.MESSAGE_PUBLISH_FAILED,
    EventType.MEMORY_ALLOCATION_FAILED,
})
DEPLOY_EVENT_TYPES = frozenset({EventType.DEPLOYMENT_STARTED, EventType.DEPLOYMENT_COMPLETED})
RESTART_EVENT_TYPES = frozenset({
    EventType.SERVICE_RESTART, EventType.OOM_KILLED, EventType.PROCESS_KILLED, EventType.SERVICE_STARTED,
})
CHANGE_ONLY_TYPES = frozenset({
    EventType.CONFIG_CHANGE, EventType.FEATURE_FLAG_CHANGE, EventType.AUTOSCALING,
    EventType.SCHEDULED_JOB_STARTED, EventType.SCHEDULED_JOB_FINISHED,
})
HEALTH_EVENT_TYPES = frozenset({EventType.HEALTH_CHECK_FAILED})


def evidence_type_for_log(event: LogEvent) -> EvidenceType:
    if event.event_type in DEPLOY_EVENT_TYPES:
        return EvidenceType.DEPLOYMENT_EVENT
    if event.event_type in RESTART_EVENT_TYPES:
        return EvidenceType.RESTART_EVENT
    if event.event_type in CHANGE_ONLY_TYPES:
        return EvidenceType.CHANGE_EVENT
    if event.event_type in TIMEOUT_EVENT_TYPES:
        return EvidenceType.TIMEOUT_EVENT
    if event.event_type in HEALTH_EVENT_TYPES:
        return EvidenceType.HEALTH_EVENT
    if event.event_type in ERROR_EVENT_TYPES or event.level is LogLevel.ERROR:
        return EvidenceType.ERROR_EVENT
    return EvidenceType.LOG_EVENT


def is_relevant_log(event: LogEvent) -> bool:
    """True when the log itself is worth keeping, regardless of any evaluation label."""
    if event.event_type in RARE_EVENT_TYPES:
        return True
    if event.event_type in RELEVANT_EVENT_TYPES and event.level in (LogLevel.WARN, LogLevel.ERROR):
        return True
    return False


def is_change_log(event: LogEvent) -> bool:
    return event.event_type in CHANGE_EVENT_TYPES


def _truncate(message: str, limit: int = 180) -> str:
    message = " ".join(message.split())
    return message if len(message) <= limit else message[: limit - 3] + "..."


def log_summary(event: LogEvent, count: int = 1, last: datetime | None = None) -> str:
    label = event.event_type.value.replace("_", " ")
    head = f"Observed {event.level.value} {label} on {event.service}"
    if count > 1 and last is not None:
        head += f" ({count} records, last at {last.isoformat()})"
    return f"{head}: {_truncate(event.message)}"


def anomaly_point_summary(point: AnomalyPoint) -> str:
    z = f"|z|={abs(point.z_score):.1f}" if point.z_score is not None else "z-score unavailable"
    base = (f"baseline {point.baseline_mean:.1f}" if point.baseline_mean is not None else "no baseline yet")
    direction = f", {point.direction.value}" if point.direction is not None else ""
    return (f"Observed {point.metric_name}={point.value:.1f} on {point.service} "
            f"({z}, {base}{direction}; {point.detection_method.value})")


def anomaly_window_summary(window: AnomalyWindow) -> str:
    peak = f"{window.peak_service} {window.peak_metric}"
    z = f"|z|={window.peak_deviation:.1f}" if window.peak_deviation is not None else "no z-score"
    return (f"Observed anomaly window on {', '.join(window.affected_services)} "
            f"({window.anomaly_count} points, peak {peak} {z}, {window.duration_minutes:.1f} min)")


class EvidenceIdFactory:
    """Per-incident sequential IDs: LOG-000001, ANOM-000001, ANOMWIN-000001."""

    def __init__(self):
        self._counts: dict[str, int] = defaultdict(int)

    def next(self, prefix: str) -> str:
        self._counts[prefix] += 1
        return f"{prefix}-{self._counts[prefix]:06d}"


def collapse_logs(events: Sequence[LogEvent]) -> list[tuple[LogEvent, int, datetime]]:
    """Keep rare logs individually. Collapse high-volume types to first+count per service and type."""
    rare: list[tuple[LogEvent, int, datetime]] = []
    buckets: dict[tuple[str, EventType], list[LogEvent]] = defaultdict(list)
    for event in events:
        if event.event_type in COLLAPSE_EVENT_TYPES:
            buckets[(event.service, event.event_type)].append(event)
        else:
            rare.append((event, 1, event.timestamp))
    collapsed = []
    for group in buckets.values():
        group = sorted(group, key=lambda e: (e.timestamp, e.message))
        collapsed.append((group[0], len(group), group[-1].timestamp))
    return sorted(rare + collapsed, key=lambda row: (row[0].timestamp, row[0].service, row[0].event_type.value))


def first_anomaly_per_series(points: Sequence[AnomalyPoint]) -> list[AnomalyPoint]:
    """Earliest point of each (service, metric) series, so the timeline shows onset, not every minute."""
    first: dict[tuple[str, str], AnomalyPoint] = {}
    for point in sorted(points, key=lambda p: (p.timestamp, p.service, p.metric_name)):
        key = (point.service, point.metric_name)
        if key not in first:
            first[key] = point
    return sorted(first.values(), key=lambda p: (p.timestamp, p.service, p.metric_name))


def notable_onsets(points: Sequence[AnomalyPoint], alerting_service: str,
                   windows: Sequence[AnomalyWindow]) -> list[AnomalyPoint]:
    """First point of series an investigator would look at first.

    Keeps the alerting service, each window's peak series, and any series that reached HIGH.
    Other series remain listed on ``AnomalyWindow.affected_series``.
    """
    peaks = {(w.peak_service, w.peak_metric) for w in windows}
    keep = []
    for point in first_anomaly_per_series(points):
        if (point.service == alerting_service or (point.service, point.metric_name) in peaks
                or point.severity is AnomalySeverity.HIGH):
            keep.append(point)
    return keep


def logs_near_window(logs: Iterable[LogEvent], window: AnomalyWindow, link_minutes: float) -> list[LogEvent]:
    return [event for event in logs if near_window(event.timestamp, window, link_minutes)]
