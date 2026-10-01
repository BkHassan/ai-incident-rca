"""Temporal correlation: observed logs and anomalies become a timeline and citable evidence.

    from correlation import correlate_incident

The layer records what happened and in what order. It does not rank diagnoses and does not
read evaluation-label fields.
"""

from .evidence import is_relevant_log
from .models import (
    CorrelationConfig,
    CorrelatedEvent,
    EvidenceItem,
    EvidenceType,
    IncidentTimeline,
    SourceType,
    TimelineEvent,
)
from .temporal import investigation_span
from .timeline import DEFAULT_CONFIG, correlate_incident

__all__ = [
    "correlate_incident", "DEFAULT_CONFIG", "CorrelationConfig",
    "IncidentTimeline", "TimelineEvent", "EvidenceItem", "CorrelatedEvent",
    "SourceType", "EvidenceType", "is_relevant_log", "investigation_span",
]
