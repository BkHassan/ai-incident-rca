"""Group anomaly points into anomaly windows: periods of abnormal behaviour within an incident."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import timedelta

from .models import AnomalyPoint, AnomalyWindow


def _strength(point: AnomalyPoint) -> tuple[float, int]:
    return (abs(point.z_score) if point.z_score is not None else -1.0, point.severity.rank)


def _window(points: list[AnomalyPoint]) -> AnomalyWindow:
    peak = max(points, key=_strength)
    start, end = points[0].timestamp, points[-1].timestamp
    return AnomalyWindow(
        incident_id=peak.incident_id,
        start_time=start,
        end_time=end,
        duration_minutes=(end - start).total_seconds() / 60,
        severity=max((p.severity for p in points), key=lambda s: s.rank),
        anomaly_count=len(points),
        affected_services=tuple(sorted({p.service for p in points})),
        affected_metrics=tuple(sorted({p.metric_name for p in points})),
        affected_series=tuple(sorted({p.series for p in points})),
        peak_deviation=abs(peak.z_score) if peak.z_score is not None else None,
        peak_z_score=peak.z_score,
        peak_metric=peak.metric_name,
        peak_service=peak.service,
        peak_timestamp=peak.timestamp,
        detection_methods=tuple(sorted({p.detection_method for p in points})),
    )


def build_anomaly_windows(points: Iterable[AnomalyPoint], max_gap_minutes: float = 2.0) -> list[AnomalyWindow]:
    """Merge the anomaly points of each incident into windows.

    Points are merged across services and metrics, and a new window starts when the next point
    comes more than ``max_gap_minutes`` after the last one. Windows are returned in time order.
    """
    gap = timedelta(minutes=max_gap_minutes)
    by_incident: dict[str, list[AnomalyPoint]] = defaultdict(list)
    for point in points:
        by_incident[point.incident_id].append(point)
    windows: list[AnomalyWindow] = []
    for incident_points in by_incident.values():
        incident_points.sort(key=lambda p: (p.timestamp, p.service, p.metric_name))
        current = [incident_points[0]]
        for point in incident_points[1:]:
            if point.timestamp - current[-1].timestamp > gap:
                windows.append(_window(current))
                current = []
            current.append(point)
        windows.append(_window(current))
    return sorted(windows, key=lambda w: (w.incident_id, w.start_time))
