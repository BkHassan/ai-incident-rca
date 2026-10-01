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

    anomalies_available, windows = _windows(incident_id, data_dir)
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


def _windows(incident_id: str, data_dir: Path) -> tuple[bool, list[WindowEvidence]]:
    path = data_dir / "derived" / "anomalies" / f"{incident_id}.json"
    if not path.is_file():
        return False, []
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
    return True, windows


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
    events = [
        TimelineEvidence(
            timestamp=event.timestamp.isoformat(),
            title=event.title,
            service=event.service,
            source_type=event.source_type.value,
            evidence_id=event.evidence_id,
            severity=event.severity,
        )
        for event in timeline.events
    ]
    return True, list(timeline.involved_services), events
