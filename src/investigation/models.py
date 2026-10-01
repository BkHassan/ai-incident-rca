"""Structured RCA models.

``confidence`` is an uncalibrated score the model assigns so hypotheses can be ranked.
It is not a probability and it is not calibrated against this dataset.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
# Uncalibrated ranking score. NaN and infinities are not scores.
Confidence = Annotated[float, Field(ge=0.0, le=1.0, allow_inf_nan=False)]
# Names that belong only on an evaluation record. RCAResult must not grow these fields.
GROUND_TRUTH_FIELD_NAMES = frozenset({
    "true_root_cause",
    "scenario",
    "root_cause_service",
    "root_cause_variant",
    "fault_start_time",
    "expected_symptoms",
    "resolution",
})


class EvidenceSource(StrEnum):
    LOG = "LOG"
    METRIC_ANOMALY = "METRIC_ANOMALY"
    ANOMALY_WINDOW = "ANOMALY_WINDOW"
    HISTORICAL_INCIDENT = "HISTORICAL_INCIDENT"
    TECHNICAL_DOCUMENT = "TECHNICAL_DOCUMENT"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


def _clean_evidence_id(value: str) -> str:
    """An evidence id is a citation key, not a free-text observation."""
    if not isinstance(value, str):
        raise ValueError("evidence id must be a string")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("evidence id must be non-empty")
    return cleaned


def _clean_evidence_ids(values: list[str]) -> list[str]:
    return [_clean_evidence_id(value) for value in values]


class RootCauseHypothesis(_Model):
    cause: str = Field(min_length=1)
    confidence: Confidence = Field(
        description="Uncalibrated model score in [0, 1]. Not a probability.",
    )
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    contradicting_evidence_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)

    @field_validator("supporting_evidence_ids", "contradicting_evidence_ids")
    @classmethod
    def _ids(cls, values: list[str]) -> list[str]:
        return _clean_evidence_ids(values)


class EvidenceReference(_Model):
    """Pointer to one supplied evidence id. Membership is checked later, not here."""

    evidence_id: str
    source_type: EvidenceSource
    short_description: str = Field(min_length=1)

    @field_validator("evidence_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _clean_evidence_id(value)


class RecommendedAction(_Model):
    action: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    evidence_ids: list[str] = Field(default_factory=list)

    @field_validator("evidence_ids")
    @classmethod
    def _ids(cls, values: list[str]) -> list[str]:
        return _clean_evidence_ids(values)


class SimilarIncident(_Model):
    incident_id: str = Field(min_length=1)
    similarity_note: str = Field(min_length=1)


class TimelineEntry(_Model):
    evidence_id: str
    timestamp: str = ""
    description: str = Field(min_length=1)

    @field_validator("evidence_id")
    @classmethod
    def _id(cls, value: str) -> str:
        return _clean_evidence_id(value)


class RCAResult(_Model):
    """Validated investigation result. Evidence ids are checked again against the context."""

    incident_id: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    root_cause: RootCauseHypothesis
    confidence: Confidence = Field(
        description="Same uncalibrated score as root_cause.confidence. Not a probability.",
    )
    alternative_causes: list[RootCauseHypothesis] = Field(default_factory=list)
    supporting_evidence: list[EvidenceReference] = Field(default_factory=list)
    contradicting_evidence: list[EvidenceReference] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    recommended_actions: list[RecommendedAction] = Field(default_factory=list)
    similar_incidents: list[SimilarIncident] = Field(default_factory=list)

    @model_validator(mode="after")
    def _consistent(self) -> RCAResult:
        overlap = GROUND_TRUTH_FIELD_NAMES & set(type(self).model_fields)
        if overlap:
            raise ValueError(f"RCAResult must not carry evaluation fields {sorted(overlap)}")
        if abs(self.confidence - self.root_cause.confidence) > 1e-6:
            raise ValueError("confidence must match root_cause.confidence")
        if self.root_cause.cause != INSUFFICIENT_EVIDENCE and not self.root_cause.supporting_evidence_ids:
            raise ValueError("a stated root cause needs at least one supporting evidence id")
        return self


class CitedEvidence(_Model):
    """One piece of evidence the investigator is allowed to cite."""

    evidence_id: str
    source_type: EvidenceSource
    short_description: str
    detail: str
    timestamp: str = ""


class InvestigationContext(_Model):
    """Compact, deterministic view of one incident. No evaluation labels."""

    incident_id: str
    service: str
    severity: str
    title: str
    description: str
    alert_start: str
    alert_end: str
    duration_minutes: float
    involved_services: list[str]
    retrieval_query: str
    evidence: list[CitedEvidence]

    def allowed_ids(self) -> dict[str, CitedEvidence]:
        return {item.evidence_id: item for item in self.evidence}


class InvestigationError(Exception):
    """Base error safe to show to an API client. It must not contain secrets."""

    code = "investigation_failed"

    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(detail)


class IncidentNotFound(InvestigationError):
    code = "not_found"


class ConfigurationError(InvestigationError):
    code = "configuration_error"


class VectorStoreMissing(InvestigationError):
    code = "vector_store_missing"


class RetrievalFailed(InvestigationError):
    code = "retrieval_failed"


class InvestigationFailed(InvestigationError):
    code = "investigation_failed"


class InvalidRCA(InvestigationError):
    code = "invalid_rca"
