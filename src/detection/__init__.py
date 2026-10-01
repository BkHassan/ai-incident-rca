"""Explainable statistical anomaly detection on normalized metrics.

    from detection import detect_anomalies, build_anomaly_windows, detect_incident

The detector reads only ``MetricPoint`` objects from the ingestion layer, never ground truth.
It flags observations that deviate from a causal rolling baseline (a z-score together with a
practical-significance floor) or that cross an optional static threshold. It then groups the
flagged points into anomaly windows.
"""

from .baseline import BaselineStats, CausalBaseline, causal_rolling_baseline
from .detector import DEFAULT_CONFIG, count_series, detect_anomalies, detect_incident
from .models import (
    DETECTOR_NAME,
    DETECTOR_VERSION,
    AnomalyPoint,
    AnomalySeverity,
    AnomalyWindow,
    DetectionMethod,
    DetectorConfig,
    Direction,
    IncidentAnomalyReport,
    MetricRule,
    SeverityThresholds,
)
from .statistical import score_observation, severity_for_z, zscore
from .windowing import build_anomaly_windows

__all__ = [
    "detect_anomalies", "build_anomaly_windows", "detect_incident", "count_series", "DEFAULT_CONFIG",
    "AnomalyPoint", "AnomalyWindow", "IncidentAnomalyReport", "AnomalySeverity", "DetectionMethod", "Direction",
    "DetectorConfig", "MetricRule", "SeverityThresholds", "DETECTOR_NAME", "DETECTOR_VERSION",
    "BaselineStats", "CausalBaseline", "causal_rolling_baseline", "score_observation", "severity_for_z", "zscore",
]
