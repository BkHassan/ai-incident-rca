"""Build an observational incident timeline from logs and Day 5 anomaly output.

The layer records order and proximity. It does not infer that an earlier event produced a later one.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from detection.models import AnomalyPoint, AnomalyWindow, IncidentAnomalyReport
from ingestion.models import IncidentEvidenceBundle, LogEvent

from .evidence import (
    EvidenceIdFactory,
    RARE_EVENT_TYPES,
    anomaly_point_summary,
    anomaly_window_summary,
    collapse_logs,
    evidence_type_for_log,
    is_change_log,
    is_relevant_log,
    log_summary,
    notable_onsets,
)
from .models import (
    CorrelationConfig,
    EvidenceItem,
    EvidenceType,
    IncidentTimeline,
    SourceType,
    TimelineEvent,
)
from .temporal import (
    change_span,
    in_span,
    investigation_span,
    log_is_near_any_window,
    select_points,
    select_windows,
)

DEFAULT_CONFIG = CorrelationConfig()

_CAUSAL_PHRASES = (" caused ", " causing ", " because ", " due to ", " led to ", " root cause",
                   " responsible for ", " triggered ", " resulting from ")


def _observational(text: str) -> str:
    lower = f" {text.lower()} "
    for phrase in _CAUSAL_PHRASES:
        if phrase in lower:
            raise ValueError(f"causal language is not allowed in correlation output: {text!r}")
    return text


_SOURCE_RANK = {SourceType.LOG: 0, SourceType.METRIC_ANOMALY: 1, SourceType.ANOMALY_WINDOW: 2}


def _sort_key_event(event: TimelineEvent) -> tuple:
    return (event.timestamp, _SOURCE_RANK[event.source_type], event.service, event.evidence_id)


def _sort_key_item(item: EvidenceItem) -> tuple:
    return (item.timestamp, _SOURCE_RANK[item.source_type], item.service, item.evidence_id)


def _item_overlaps_window(item: EvidenceItem, window: AnomalyWindow, link_minutes: float) -> bool:
    pad = timedelta(minutes=link_minutes)
    last = item.last_timestamp or item.timestamp
    return item.timestamp <= window.end_time + pad and last >= window.start_time - pad


def _select_logs(bundle: IncidentEvidenceBundle, windows: list[AnomalyWindow],
                 config: CorrelationConfig) -> list[LogEvent]:
    inv_start, inv_end = investigation_span(bundle.context, config)
    chg_start, chg_end = change_span(bundle.context, config)
    window_services = {s for w in windows for s in w.affected_services}
    alerting = bundle.context.service
    selected = []
    for event in bundle.logs:
        if event.incident_id != bundle.incident_id or not is_relevant_log(event):
            continue
        near = log_is_near_any_window(event, windows, config.log_to_window_link_minutes)
        if is_change_log(event) and in_span(event.timestamp, chg_start, chg_end):
            selected.append(event)
        elif event.event_type in RARE_EVENT_TYPES and in_span(event.timestamp, inv_start, inv_end):
            selected.append(event)
        elif near:
            selected.append(event)
        elif in_span(event.timestamp, inv_start, inv_end) and (
            not windows or event.service in window_services | {alerting}
        ):
            selected.append(event)
    return selected


def _window_item(window: AnomalyWindow, evidence_id: str, related: tuple[str, ...]) -> EvidenceItem:
    summary = _observational(anomaly_window_summary(window))
    return EvidenceItem(
        evidence_id=evidence_id, timestamp=window.start_time, incident_id=window.incident_id,
        service=window.peak_service, source_type=SourceType.ANOMALY_WINDOW,
        evidence_type=EvidenceType.ANOMALY_WINDOW, summary=summary,
        source_reference=f"anomaly_window:{window.start_time.isoformat()}:{window.end_time.isoformat()}"
                         f":{window.peak_service}:{window.peak_metric}",
        metric_name=window.peak_metric, severity=window.severity.value,
        occurrence_count=window.anomaly_count, last_timestamp=window.end_time,
        related_evidence_ids=related,
    )


def _point_item(point: AnomalyPoint, evidence_id: str) -> EvidenceItem:
    summary = _observational(anomaly_point_summary(point))
    return EvidenceItem(
        evidence_id=evidence_id, timestamp=point.timestamp, incident_id=point.incident_id,
        service=point.service, source_type=SourceType.METRIC_ANOMALY, evidence_type=EvidenceType.ANOMALY,
        summary=summary,
        source_reference=f"anomaly:{point.service}:{point.metric_name}:{point.timestamp.isoformat()}",
        metric_name=point.metric_name, severity=point.severity.value,
    )


def _log_item(event: LogEvent, count: int, last: datetime, evidence_id: str) -> EvidenceItem:
    # Raw log text is quoted as-is; it may contain phrases such as "due to" that are not ours.
    summary = log_summary(event, count, last if count > 1 else None)
    return EvidenceItem(
        evidence_id=evidence_id, timestamp=event.timestamp, incident_id=event.incident_id,
        service=event.service, source_type=SourceType.LOG, evidence_type=evidence_type_for_log(event),
        summary=summary,
        source_reference=f"log:{event.service}:{event.timestamp.isoformat()}:{event.event_type.value}",
        event_type=event.event_type, severity=event.level.value, occurrence_count=count,
        last_timestamp=last if count > 1 else None,
    )


def _timeline_event(item: EvidenceItem) -> TimelineEvent:
    if item.evidence_type is EvidenceType.ANOMALY_WINDOW:
        title = f"anomaly window ({item.metric_name}) on {item.service}"
    elif item.evidence_type is EvidenceType.ANOMALY:
        title = f"{item.metric_name} anomaly on {item.service}"
    else:
        label = item.event_type.value.replace("_", " ") if item.event_type is not None else "log event"
        extra = f" x{item.occurrence_count}" if item.occurrence_count > 1 else ""
        title = f"{label} on {item.service}{extra}"
    return TimelineEvent(
        timestamp=item.timestamp, title=_observational(title), description=item.summary,
        service=item.service, source_type=item.source_type, evidence_id=item.evidence_id,
        severity=item.severity,
    )


def correlate_incident(bundle: IncidentEvidenceBundle, anomalies: IncidentAnomalyReport,
                       config: CorrelationConfig = DEFAULT_CONFIG) -> IncidentTimeline:
    """Combine an evidence bundle with its anomaly report. Neither argument may carry ground truth."""
    if bundle.incident_id != anomalies.incident_id:
        raise ValueError(f"bundle is {bundle.incident_id} but anomaly report is {anomalies.incident_id}")
    inv_start, inv_end = investigation_span(bundle.context, config)
    windows = select_windows(anomalies.windows, inv_start, inv_end)
    points = select_points(anomalies.points, inv_start, inv_end, windows=[])
    logs = _select_logs(bundle, windows, config)

    ids = EvidenceIdFactory()
    log_items = [_log_item(event, count, last, ids.next("LOG"))
                 for event, count, last in collapse_logs(logs)]
    point_items = [_point_item(point, ids.next("ANOM"))
                   for point in notable_onsets(points, bundle.context.service, windows)]
    window_items = []
    for window in windows:
        nearby = tuple(item.evidence_id for item in log_items
                       if _item_overlaps_window(item, window, config.log_to_window_link_minutes))
        window_items.append(_window_item(window, ids.next("ANOMWIN"), nearby))

    evidence = tuple(sorted(log_items + point_items + window_items, key=_sort_key_item))
    events = tuple(sorted((_timeline_event(item) for item in evidence), key=_sort_key_event))
    services = tuple(sorted({item.service for item in evidence}))
    first = events[0] if events else None
    earliest_log = next((e for e in events if e.source_type is SourceType.LOG), None)
    earliest_anomaly = next((e for e in events if e.source_type is not SourceType.LOG), None)
    return IncidentTimeline(
        incident_id=bundle.incident_id, alerting_service=bundle.context.service,
        start_time=bundle.context.start_time, end_time=bundle.context.end_time,
        investigation_start=inv_start, investigation_end=inv_end, events=events,
        evidence_items=evidence, involved_services=services, first_observed_event=first,
        earliest_relevant_log=earliest_log, earliest_anomaly=earliest_anomaly,
        anomaly_windows=tuple(windows), config=config,
    )
