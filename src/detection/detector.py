"""Detector API: metric points in, anomaly points out.

The detector only accepts ``MetricPoint`` objects and, for a whole incident, an
``IncidentEvidenceBundle``. Both come from the ingestion layer and contain no ground truth.
Every applicable metric of every service is analyzed with the same rules; no series is chosen
by what the incident is expected to show.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from ingestion.models import METRIC_FIELDS, IncidentEvidenceBundle, MetricPoint

from .baseline import CausalBaseline
from .models import AnomalyPoint, AnomalySeverity, DetectionMethod, DetectorConfig, IncidentAnomalyReport
from .statistical import Score, score_observation, severity_for_z
from .windowing import build_anomaly_windows

DEFAULT_CONFIG = DetectorConfig()


def _series(metrics: Iterable[MetricPoint]) -> dict[tuple[str, str, str], list[tuple]]:
    """Group observations by (incident, service, metric) in time order, skipping ``None`` values."""
    series: dict[tuple[str, str, str], list[tuple]] = defaultdict(list)
    for point in sorted(metrics, key=lambda p: (p.incident_id, p.service, p.timestamp)):
        for metric in METRIC_FIELDS:
            value = getattr(point, metric)
            if value is not None:
                series[(point.incident_id, point.service, metric)].append((point.timestamp, value))
    return series


def _severity(score: Score, config: DetectorConfig) -> AnomalySeverity:
    candidates = []
    if score.method in (DetectionMethod.ROLLING_ZSCORE, DetectionMethod.DRIFT_ZSCORE):
        candidates.append(severity_for_z(score.reported.z_score, config.severity))
    if score.threshold_exceeded:
        candidates.append(config.absolute_threshold_severity)
    return max(candidates, key=lambda s: s.rank)


def detect_anomalies(metrics: Iterable[MetricPoint], config: DetectorConfig = DEFAULT_CONFIG) -> list[AnomalyPoint]:
    """Score every applicable metric observation against its causal baselines.

    Returns anomaly points sorted by timestamp, service and metric. Each (service, metric) series
    has its own baselines. Observations are scored in time order, and each is compared only with
    the observations before it.
    """
    points: list[AnomalyPoint] = []
    for (incident_id, service, metric), observations in _series(metrics).items():
        rule = config.metrics.get(metric)
        if rule is None or not rule.enabled:
            continue
        baseline = CausalBaseline(config.baseline_window, config.min_baseline_points, max_lag=config.drift_lag)
        for timestamp, value in observations:
            lagged = baseline.lagged(config.drift_lag) if config.drift_lag else None
            score = score_observation(value, baseline.recent(), lagged, rule, config.z_threshold)
            if score.is_anomaly:
                cmp = score.reported
                points.append(AnomalyPoint(
                    incident_id=incident_id, timestamp=timestamp, service=service, metric_name=metric, value=value,
                    baseline_mean=cmp.baseline.mean if cmp else None, baseline_std=cmp.baseline.std if cmp else None,
                    baseline_points=cmp.baseline.count if cmp else 0, z_score=cmp.z_score if cmp else None,
                    deviation=cmp.deviation if cmp else None, direction=cmp.direction if cmp else None,
                    severity=_severity(score, config), detection_method=score.method,
                    absolute_threshold_exceeded=score.threshold_exceeded))
            if not (score.is_anomaly and config.exclude_anomalies_from_baseline):
                baseline.add(value)
    return sorted(points, key=lambda p: (p.timestamp, p.service, p.metric_name))


def count_series(metrics: Iterable[MetricPoint], config: DetectorConfig = DEFAULT_CONFIG) -> tuple[int, int]:
    """Return the number of (series, observations) the detector analyzes."""
    series = [obs for (_, _, metric), obs in _series(metrics).items()
              if metric in config.metrics and config.metrics[metric].enabled]
    return len(series), sum(len(obs) for obs in series)


def detect_incident(bundle: IncidentEvidenceBundle, config: DetectorConfig = DEFAULT_CONFIG) -> IncidentAnomalyReport:
    """Run the detector on one incident's metrics and group the anomaly points into windows."""
    points = detect_anomalies(bundle.metrics, config)
    windows = build_anomaly_windows(points, max_gap_minutes=config.window_max_gap_minutes)
    n_series, n_obs = count_series(bundle.metrics, config)
    return IncidentAnomalyReport(incident_id=bundle.incident_id, config=config, series_analyzed=n_series,
                                 observations_analyzed=n_obs, points=tuple(points), windows=tuple(windows))
