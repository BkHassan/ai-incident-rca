"""Observed-evidence models for temporal correlation.

These objects describe what was seen and when. They do not name an evaluation label, and
generated summaries must not claim that one event produced another.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from detection.models import AnomalyWindow
from ingestion.models import EventType

PositiveInt = Annotated[int, Field(ge=1)]
NonNegativeFloat = Annotated[float, Field(ge=0, allow_inf_nan=False)]


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class SourceType(StrEnum):
    LOG = "LOG"
    METRIC_ANOMALY = "METRIC_ANOMALY"
    ANOMALY_WINDOW = "ANOMALY_WINDOW"


class EvidenceType(StrEnum):
    """Kind of observed fact. None of these names an evaluation label."""

    LOG_EVENT = "LOG_EVENT"
    ERROR_EVENT = "ERROR_EVENT"
    TIMEOUT_EVENT = "TIMEOUT_EVENT"
    DEPLOYMENT_EVENT = "DEPLOYMENT_EVENT"
    CHANGE_EVENT = "CHANGE_EVENT"
    RESTART_EVENT = "RESTART_EVENT"
    HEALTH_EVENT = "HEALTH_EVENT"
    ANOMALY = "ANOMALY"
    ANOMALY_WINDOW = "ANOMALY_WINDOW"


class CorrelationConfig(_Frozen):
    """Time windows and relevance knobs. Defaults are MVP heuristics for this 1-minute dataset."""

    lookback_minutes: NonNegativeFloat = 30.0
    after_pad_minutes: NonNegativeFloat = 10.0
    # Lifecycle / change logs (deploy, restart, config, flags, autoscaling) use a longer lookback
    # because they are rare and often the only INFO context before the alert.
    change_lookback_minutes: NonNegativeFloat = 90.0
    # A log is "near" an anomaly window if it falls in [start - this, end + this].
    log_to_window_link_minutes: NonNegativeFloat = 5.0

    @model_validator(mode="after")
    def _lookbacks(self) -> CorrelationConfig:
        if self.change_lookback_minutes < self.lookback_minutes:
            raise ValueError("change_lookback_minutes must be >= lookback_minutes")
        return self


class CorrelatedEvent(_Frozen):
    """One observed record placed on a common clock: a log line or a metric anomaly."""

    timestamp: datetime
    incident_id: str
    service: str
    source_type: SourceType
    event_type: EventType | None = None
    level: str | None = None
    metric_name: str | None = None
    message: str
    source_reference: str


class EvidenceItem(_Frozen):
    """One citable observed fact. ``evidence_id`` is stable for a given incident and input order."""

    evidence_id: str
    timestamp: datetime
    incident_id: str
    service: str
    source_type: SourceType
    evidence_type: EvidenceType
    summary: str
    source_reference: str
    event_type: EventType | None = None
    metric_name: str | None = None
    severity: str | None = None
    occurrence_count: PositiveInt = 1
    last_timestamp: datetime | None = None
    related_evidence_ids: tuple[str, ...] = ()


class TimelineEvent(_Frozen):
    """One row of the incident timeline. Title and description are observational, not causal."""

    timestamp: datetime
    title: str
    description: str
    service: str
    source_type: SourceType
    evidence_id: str
    severity: str | None = None


class IncidentTimeline(_Frozen):
    """Observed sequence of relevant logs and anomalies around an incident. No ground truth."""

    incident_id: str
    alerting_service: str
    start_time: datetime  # alert start (incident context)
    end_time: datetime  # alert end
    investigation_start: datetime
    investigation_end: datetime
    events: tuple[TimelineEvent, ...]
    evidence_items: tuple[EvidenceItem, ...]
    involved_services: tuple[str, ...]
    first_observed_event: TimelineEvent | None
    earliest_relevant_log: TimelineEvent | None
    earliest_anomaly: TimelineEvent | None
    anomaly_windows: tuple[AnomalyWindow, ...]
    config: CorrelationConfig
