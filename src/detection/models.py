"""Configuration and result models for statistical anomaly detection.

These models describe observed deviations only. They carry no labels and no fault timing, and
``extra="forbid"`` prevents such fields from being added through input data.

Every numeric default is an MVP heuristic chosen for this synthetic dataset's units, not an
industry standard. Change it through ``DetectorConfig``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ingestion.models import METRIC_FIELDS

MetricName = Literal["cpu_usage", "memory_usage", "request_rate", "latency_ms", "error_rate",
                     "db_connection_utilization", "downstream_latency_ms"]
if set(get_args(MetricName)) != set(METRIC_FIELDS):
    raise ImportError("detection.models.MetricName is out of sync with ingestion.models.METRIC_FIELDS")

PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]

DETECTOR_NAME = "rolling_zscore"
DETECTOR_VERSION = "1.0.0"


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnomalySeverity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {AnomalySeverity.LOW: 1, AnomalySeverity.MEDIUM: 2, AnomalySeverity.HIGH: 3}


class DetectionMethod(StrEnum):
    ROLLING_ZSCORE = "rolling_zscore"  # z-score against the recent baseline
    DRIFT_ZSCORE = "drift_zscore"  # z-score against the lagged baseline
    ABSOLUTE_THRESHOLD = "absolute_threshold"


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"


# --------------------------------------------------------------------------- configuration


class MetricRule(_Frozen):
    """How one metric is scored.

    A z-score anomaly needs both statistical and practical significance:
    ``|z| >= z_threshold`` and ``|value - mean| >= max(min_abs_deviation, min_rel_deviation * |mean|)``.
    The deviation floor stops tiny wobbles on very stable series from counting as anomalies.
    """

    enabled: bool = True
    directions: tuple[Direction, ...] = (Direction.UP, Direction.DOWN)
    min_std: PositiveFloat
    min_abs_deviation: NonNegativeFloat = 0.0
    min_rel_deviation: NonNegativeFloat = 0.0
    # Static ceiling, e.g. saturation of a percentage-of-capacity metric. The same value applies
    # to every service and every incident.
    absolute_threshold: float | None = None


class SeverityThresholds(_Frozen):
    """Lower bounds of ``|z|`` for each severity; ``|z|`` below ``medium`` is LOW.

    These are heuristic MVP values set from the unlabeled distribution of anomaly ``|z|`` on this
    dataset. The first defaults (5 and 10) rated about 80% of points HIGH. See
    docs/anomaly_detection.md.
    """

    medium: PositiveFloat = 10.0
    high: PositiveFloat = 50.0

    @model_validator(mode="after")
    def _ordered(self) -> SeverityThresholds:
        if not self.medium < self.high:
            raise ValueError("severity thresholds must satisfy medium < high")
        return self


def _default_rules() -> dict[str, MetricRule]:
    return {
        "cpu_usage": MetricRule(min_std=0.5, min_abs_deviation=10.0, absolute_threshold=90.0),
        "memory_usage": MetricRule(min_std=0.25, min_abs_deviation=5.0, absolute_threshold=90.0),
        "request_rate": MetricRule(min_std=1.0, min_rel_deviation=0.3),
        "latency_ms": MetricRule(min_std=2.0, min_abs_deviation=20.0, min_rel_deviation=0.5),
        "error_rate": MetricRule(min_std=0.05, min_abs_deviation=1.0),
        "db_connection_utilization": MetricRule(min_std=0.5, min_abs_deviation=10.0, absolute_threshold=90.0),
        "downstream_latency_ms": MetricRule(min_std=2.0, min_abs_deviation=20.0, min_rel_deviation=0.5),
    }


class DetectorConfig(_Frozen):
    """All tunable parameters of the detector. The defaults are MVP heuristics."""

    baseline_window: Annotated[int, Field(ge=2)] = 15
    min_baseline_points: Annotated[int, Field(ge=2)] = 10
    z_threshold: PositiveFloat = 3.0
    # The lagged baseline has baseline_window observations that end drift_lag accepted
    # observations before the current one. A recent window moves with a gradual ramp, so the ramp
    # never deviates much from it; the lagged window does not move with it. 0 disables this check.
    drift_lag: Annotated[int, Field(ge=0)] = 30
    severity: SeverityThresholds = SeverityThresholds()
    # Leave observations already flagged as anomalous out of later baselines, so a sustained
    # shift stays anomalous instead of becoming the new normal. The baseline still uses past
    # observations only.
    exclude_anomalies_from_baseline: bool = True
    # Severity of a point flagged only by an absolute threshold (no z-score anomaly).
    absolute_threshold_severity: AnomalySeverity = AnomalySeverity.MEDIUM
    metrics: dict[str, MetricRule] = Field(default_factory=_default_rules)
    # Anomaly points at most this many minutes apart join the same window.
    window_max_gap_minutes: NonNegativeFloat = 2.0

    @model_validator(mode="after")
    def _check(self) -> DetectorConfig:
        if self.min_baseline_points > self.baseline_window:
            raise ValueError("min_baseline_points cannot exceed baseline_window")
        unknown = set(self.metrics) - set(METRIC_FIELDS)
        if unknown:
            raise ValueError(f"rules for unknown metrics {sorted(unknown)}")
        return self


# --------------------------------------------------------------------------- results


class AnomalyPoint(_Frozen):
    """One metric observation that deviates from a causal baseline or crosses a static threshold.

    ``baseline_*``, ``z_score`` and ``deviation`` refer to the baseline that flagged the point: the
    recent one for ``rolling_zscore`` and the lagged one for ``drift_zscore``. For a point flagged
    only by an absolute threshold they refer to the recent baseline. They are ``None`` while the
    series is still warming up (fewer than ``min_baseline_points`` past observations). In that case
    only an absolute threshold can flag a point.
    """

    incident_id: str
    timestamp: datetime
    service: str
    metric_name: MetricName
    value: float
    baseline_mean: float | None
    baseline_std: float | None  # sample std of the baseline window, before the min_std floor
    baseline_points: int
    z_score: float | None  # computed with max(baseline_std, min_std)
    deviation: float | None  # value - baseline_mean
    direction: Direction | None
    severity: AnomalySeverity
    detection_method: DetectionMethod
    absolute_threshold_exceeded: bool

    @property
    def series(self) -> str:
        return f"{self.service}:{self.metric_name}"


class AnomalyWindow(_Frozen):
    """A period of an incident in which anomaly points occur with gaps of at most ``window_max_gap_minutes``."""

    incident_id: str
    start_time: datetime
    end_time: datetime
    duration_minutes: NonNegativeFloat  # end_time - start_time; 0 for a single-minute window
    severity: AnomalySeverity
    anomaly_count: Annotated[int, Field(ge=1)]
    affected_services: tuple[str, ...]
    affected_metrics: tuple[MetricName, ...]
    affected_series: tuple[str, ...]  # "service:metric"
    peak_deviation: NonNegativeFloat | None  # |z_score| of the strongest point; None if no point has a z-score
    peak_z_score: float | None
    peak_metric: MetricName
    peak_service: str
    peak_timestamp: datetime
    detection_methods: tuple[DetectionMethod, ...]


class IncidentAnomalyReport(_Frozen):
    """Detector output for one incident: the configuration used, anomaly points and windows."""

    incident_id: str
    detector: str = DETECTOR_NAME
    detector_version: str = DETECTOR_VERSION
    config: DetectorConfig
    series_analyzed: int
    observations_analyzed: int
    points: tuple[AnomalyPoint, ...]
    windows: tuple[AnomalyWindow, ...]
