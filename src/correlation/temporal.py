"""Deterministic time windows and overlap checks.

All bounds come from incident-context alert times plus configurable padding, or from anomaly
windows produced by detection. Injected-fault timestamps from evaluation labels are never used.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from detection.models import AnomalyPoint, AnomalyWindow
from ingestion.models import IncidentContext, LogEvent

from .models import CorrelationConfig


def investigation_span(context: IncidentContext, config: CorrelationConfig) -> tuple[datetime, datetime]:
    """Primary investigation interval: padded alert period. Not the full case window."""
    start = context.start_time - timedelta(minutes=config.lookback_minutes)
    end = context.end_time + timedelta(minutes=config.after_pad_minutes)
    if start < context.window_start:
        start = context.window_start
    if end > context.window_end:
        end = context.window_end
    return start, end


def change_span(context: IncidentContext, config: CorrelationConfig) -> tuple[datetime, datetime]:
    """Wider interval used only for rare lifecycle / change logs."""
    start = context.start_time - timedelta(minutes=config.change_lookback_minutes)
    _, end = investigation_span(context, config)
    if start < context.window_start:
        start = context.window_start
    return start, end


def in_span(timestamp: datetime, start: datetime, end: datetime) -> bool:
    return start <= timestamp <= end


def window_overlaps_span(window: AnomalyWindow, start: datetime, end: datetime) -> bool:
    return window.start_time <= end and window.end_time >= start


def near_window(timestamp: datetime, window: AnomalyWindow, link_minutes: float) -> bool:
    pad = timedelta(minutes=link_minutes)
    return window.start_time - pad <= timestamp <= window.end_time + pad


def select_windows(windows: tuple[AnomalyWindow, ...] | list[AnomalyWindow],
                   start: datetime, end: datetime) -> list[AnomalyWindow]:
    return [w for w in windows if window_overlaps_span(w, start, end)]


def select_points(points: tuple[AnomalyPoint, ...] | list[AnomalyPoint],
                  start: datetime, end: datetime,
                  windows: list[AnomalyWindow]) -> list[AnomalyPoint]:
    """Keep points inside the investigation span or inside an overlapping anomaly window."""
    kept = []
    for point in points:
        if in_span(point.timestamp, start, end) or any(w.start_time <= point.timestamp <= w.end_time for w in windows):
            kept.append(point)
    return kept


def log_is_near_any_window(event: LogEvent, windows: list[AnomalyWindow], link_minutes: float) -> bool:
    return any(near_window(event.timestamp, window, link_minutes) for window in windows)
