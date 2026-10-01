"""Scoring one observation against its baselines: z-score, deviation floor, threshold and severity."""

from __future__ import annotations

from dataclasses import dataclass

from .baseline import BaselineStats
from .models import AnomalySeverity, DetectionMethod, Direction, MetricRule, SeverityThresholds


@dataclass(frozen=True)
class Comparison:
    """An observation compared with one baseline."""

    baseline: BaselineStats
    z_score: float
    deviation: float
    direction: Direction
    anomalous: bool


@dataclass(frozen=True)
class Score:
    """The outcome of scoring one observation.

    ``reported`` is the comparison shown on the anomaly point: the recent baseline if it fired,
    otherwise the lagged one if it fired, otherwise the recent baseline (``None`` during warm-up).
    """

    method: DetectionMethod | None
    reported: Comparison | None
    threshold_exceeded: bool

    @property
    def is_anomaly(self) -> bool:
        return self.method is not None


def zscore(value: float, baseline: BaselineStats, min_std: float) -> float:
    """``(value - mean) / max(std, min_std)``. The floor makes constant baselines safe."""
    return (value - baseline.mean) / max(baseline.std, min_std)


def compare(value: float, baseline: BaselineStats, rule: MetricRule, z_threshold: float) -> Comparison:
    z = zscore(value, baseline, rule.min_std)
    deviation = value - baseline.mean
    direction = Direction.UP if deviation >= 0 else Direction.DOWN
    floor = max(rule.min_abs_deviation, rule.min_rel_deviation * abs(baseline.mean))
    anomalous = abs(z) >= z_threshold and abs(deviation) >= floor and direction in rule.directions
    return Comparison(baseline, z, deviation, direction, anomalous)


def score_observation(value: float, recent: BaselineStats | None, lagged: BaselineStats | None,
                      rule: MetricRule, z_threshold: float) -> Score:
    threshold_exceeded = rule.absolute_threshold is not None and value >= rule.absolute_threshold
    near = compare(value, recent, rule, z_threshold) if recent is not None else None
    far = compare(value, lagged, rule, z_threshold) if lagged is not None else None
    if near is not None and near.anomalous:
        return Score(DetectionMethod.ROLLING_ZSCORE, near, threshold_exceeded)
    if far is not None and far.anomalous:
        return Score(DetectionMethod.DRIFT_ZSCORE, far, threshold_exceeded)
    method = DetectionMethod.ABSOLUTE_THRESHOLD if threshold_exceeded else None
    return Score(method, near, threshold_exceeded)


def severity_for_z(z: float, thresholds: SeverityThresholds) -> AnomalySeverity:
    """Map ``|z|`` to a severity using heuristic MVP thresholds (not an industry standard)."""
    magnitude = abs(z)
    if magnitude >= thresholds.high:
        return AnomalySeverity.HIGH
    if magnitude >= thresholds.medium:
        return AnomalySeverity.MEDIUM
    return AnomalySeverity.LOW
