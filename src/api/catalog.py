"""Read-only incident catalog.

Responses are built from ``IncidentContext``, the evidence bundle, and derived
anomaly and timeline files. Ground-truth fields are never read.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from pydantic import ValidationError

from correlation.models import IncidentTimeline
from detection.models import IncidentAnomalyReport
from ingestion import DEFAULT_DATA_DIR, incident_path, list_incident_ids, load_evidence_bundle, load_incident_context
from ingestion.errors import IngestionError
from ingestion.models import METRIC_FIELDS
from investigation.models import IncidentNotFound, InvestigationError

from .schemas import (
    IncidentDetail,
    IncidentListResponse,
    IncidentSummary,
    LogEvidence,
    MetricEvidence,
    NamedCount,
    TimelineEvidence,
    AnomalyMetricSummary,
    WindowEvidence,
)


class CatalogUnavailable(InvestigationError):
    code = "catalog_failed"


def list_catalog(data_dir: str | Path = DEFAULT_DATA_DIR) -> IncidentListResponse:
    data_dir = Path(data_dir)
    incidents = []
    for incident_id in list_incident_ids(data_dir):
        incidents.append(_summary(_context(incident_id, data_dir)))
    return IncidentListResponse(incidents=incidents)


def read_catalog_incident(incident_id: str, data_dir: str | Path = DEFAULT_DATA_DIR) -> IncidentDetail:
    data_dir = Path(data_dir)
    context = _context(incident_id, data_dir)
    try:
        bundle = load_evidence_bundle(incident_id, data_dir)
    except IngestionError as exc:
        raise CatalogUnavailable(f"Evidence for {incident_id} could not be read.") from exc
    except FileNotFoundError as exc:
        raise CatalogUnavailable(f"Evidence for {incident_id} could not be read.") from exc

    levels = Counter(event.level.value for event in bundle.logs)
    event_types = Counter(event.event_type.value for event in bundle.logs)
    series = []
    for service in sorted({point.service for point in bundle.metrics}):
        points = [point for point in bundle.metrics if point.service == service]
        for name in METRIC_FIELDS:
            if any(getattr(point, name) is not None for point in points):
                series.append(f"{service}:{name}")

    anomalies_available, windows, anomaly_metrics = _anomalies(incident_id, data_dir)
    timeline_available, observed, events = _timeline(incident_id, data_dir)
    summary = _summary(context)
    return IncidentDetail(
        **summary.model_dump(),
        window_start=context.window_start.isoformat(),
        window_end=context.window_end.isoformat(),
        logs=LogEvidence(
            line_count=len(bundle.logs),
            by_level={level: levels[level] for level in ("ERROR", "WARN", "INFO") if levels[level]},
            services=sorted({event.service for event in bundle.logs}),
            event_types=[
                NamedCount(name=name, count=count)
                for name, count in sorted(event_types.items(), key=lambda item: (-item[1], item[0]))
            ],
        ),
        metrics=MetricEvidence(
            row_count=len(bundle.metrics),
            services=sorted({point.service for point in bundle.metrics}),
            series=series,
        ),
        anomalies_available=anomalies_available,
        anomaly_windows=windows,
        anomaly_metrics=anomaly_metrics,
        timeline_available=timeline_available,
        observed_services=observed,
        timeline=events,
    )


def _context(incident_id: str, data_dir: Path):
    path = incident_path(incident_id, data_dir)
    if not path.is_file():
        raise IncidentNotFound(f"No incident {incident_id}.")
    try:
        context = load_incident_context(path)
    except IngestionError as exc:
        raise CatalogUnavailable(f"Incident {incident_id} could not be read.") from exc
    if context.incident_id != incident_id:
        raise CatalogUnavailable(f"Incident {incident_id} could not be read.")
    return context


def _summary(context) -> IncidentSummary:
    return IncidentSummary(
        incident_id=context.incident_id,
        title=context.title,
        service=context.service,
        severity=context.severity.value,
        start_time=context.start_time.isoformat(),
        end_time=context.end_time.isoformat(),
        duration_minutes=context.duration_minutes,
        description=context.description,
    )


_METRIC_ORDER = (
    "cpu_usage",
    "memory_usage",
    "request_rate",
    "latency_ms",
    "error_rate",
    "db_connection_utilization",
    "downstream_latency_ms",
)
_METRIC_LABELS = {
    "cpu_usage": "CPU",
    "memory_usage": "Memory",
    "request_rate": "Request rate",
    "latency_ms": "Latency",
    "error_rate": "Error rate",
    "db_connection_utilization": "DB connection utilization",
    "downstream_latency_ms": "Downstream latency",
}
_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _anomalies(incident_id: str, data_dir: Path) -> tuple[bool, list[WindowEvidence], list[AnomalyMetricSummary]]:
    path = data_dir / "derived" / "anomalies" / f"{incident_id}.json"
    if not path.is_file():
        return False, [], []
    try:
        report = IncidentAnomalyReport.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise CatalogUnavailable(f"Anomaly report for {incident_id} could not be read.") from exc
    if report.incident_id != incident_id:
        raise CatalogUnavailable(f"Anomaly report for {incident_id} could not be read.")
    windows = [
        WindowEvidence(
            start_time=window.start_time.isoformat(),
            end_time=window.end_time.isoformat(),
            duration_minutes=window.duration_minutes,
            severity=window.severity.value,
            anomaly_count=window.anomaly_count,
            services=list(window.affected_services),
            metrics=list(window.affected_metrics),
            peak_z_score=window.peak_z_score,
            peak_metric=window.peak_metric,
            peak_service=window.peak_service,
        )
        for window in report.windows
    ]
    return True, windows, _metric_summary(report)


def _metric_name(value: object) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _metric_summary(report: IncidentAnomalyReport) -> list[AnomalyMetricSummary]:
    point_counts: dict[str, int] = {}
    peak: dict[str, str] = {}
    for point in report.points:
        name = _metric_name(point.metric_name)
        point_counts[name] = point_counts.get(name, 0) + 1
        severity = point.severity.value
        if name not in peak or _SEVERITY_RANK.get(severity, 0) > _SEVERITY_RANK.get(peak[name], 0):
            peak[name] = severity
    window_counts: dict[str, int] = {}
    for window in report.windows:
        for metric in window.affected_metrics:
            name = _metric_name(metric)
            window_counts[name] = window_counts.get(name, 0) + 1
    names = [name for name in _METRIC_ORDER if point_counts.get(name) or window_counts.get(name)]
    extra = sorted((set(point_counts) | set(window_counts)) - set(_METRIC_ORDER))
    return [
        AnomalyMetricSummary(
            metric=name,
            label=_METRIC_LABELS.get(name, name),
            point_count=point_counts.get(name, 0),
            window_count=window_counts.get(name, 0),
            peak_severity=peak.get(name),
        )
        for name in names + extra
    ]


def _timeline(incident_id: str, data_dir: Path) -> tuple[bool, list[str], list[TimelineEvidence]]:
    path = data_dir / "derived" / "correlation" / f"{incident_id}.json"
    if not path.is_file():
        return False, [], []
    try:
        timeline = IncidentTimeline.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, ValidationError) as exc:
        raise CatalogUnavailable(f"Timeline for {incident_id} could not be read.") from exc
    if timeline.incident_id != incident_id:
        raise CatalogUnavailable(f"Timeline for {incident_id} could not be read.")
    titles = {event.evidence_id: event.title for event in timeline.events}
    events = [
        TimelineEvidence(
            timestamp=item.timestamp.isoformat(),
            title=titles.get(item.evidence_id, item.summary),
            summary=item.summary,
            service=item.service,
            source_type=item.source_type.value,
            evidence_type=item.evidence_type.value,
            evidence_id=item.evidence_id,
            severity=item.severity,
            metric_name=item.metric_name,
            event_type=item.event_type.value if item.event_type is not None else None,
            occurrence_count=item.occurrence_count,
            last_timestamp=item.last_timestamp.isoformat() if item.last_timestamp is not None else None,
            related_evidence_ids=list(item.related_evidence_ids),
        )
        for item in timeline.evidence_items
    ]
    return True, list(timeline.involved_services), events
