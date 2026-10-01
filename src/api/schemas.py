"""HTTP schemas for the investigation API.

The response body is the RCA model from ``investigation.models``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(pattern=r"^INC-\d{3}$")


class ErrorResponse(BaseModel):
    error: str
    detail: str


class IncidentSummary(BaseModel):
    """Operational alert fields. No evaluation labels."""

    model_config = ConfigDict(extra="forbid")

    incident_id: str
    title: str
    service: str
    severity: str
    start_time: str
    end_time: str
    duration_minutes: float
    description: str


class IncidentListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incidents: list[IncidentSummary]


class NamedCount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    count: int


class LogEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line_count: int
    by_level: dict[str, int]
    services: list[str]
    event_types: list[NamedCount]


class MetricEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_count: int
    services: list[str]
    series: list[str]


class WindowEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_time: str
    end_time: str
    duration_minutes: float
    severity: str
    anomaly_count: int
    services: list[str]
    metrics: list[str]
    peak_z_score: float | None
    peak_metric: str
    peak_service: str


class TimelineEvidence(BaseModel):
    """One correlated evidence item. Logs are already collapsed; anomaly points are onsets, not every minute."""

    model_config = ConfigDict(extra="forbid")

    timestamp: str
    title: str
    summary: str
    service: str
    source_type: str
    evidence_type: str
    evidence_id: str
    severity: str | None
    metric_name: str | None = None
    event_type: str | None = None
    occurrence_count: int = 1
    last_timestamp: str | None = None
    related_evidence_ids: list[str] = Field(default_factory=list)


class AnomalyMetricSummary(BaseModel):
    """Counts for one metric. Points themselves are not included."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    label: str
    point_count: int
    window_count: int
    peak_severity: str | None = None


class IncidentDetail(IncidentSummary):
    window_start: str
    window_end: str
    logs: LogEvidence
    metrics: MetricEvidence
    anomalies_available: bool
    anomaly_windows: list[WindowEvidence]
    anomaly_metrics: list[AnomalyMetricSummary]
    timeline_available: bool
    observed_services: list[str]
    timeline: list[TimelineEvidence]
