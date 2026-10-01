"""Ingestion layer: raw incident, log and metric files become validated, normalized Python objects.

Investigation code should use ``load_evidence_bundle``, which returns context, logs and metrics
and never ground truth. Evaluation code uses ``load_ground_truth`` or ``load_evaluation_record``.
"""

from .errors import IngestionError, RecordIssue
from .incident_loader import (
    CONTEXT_FIELDS,
    DEFAULT_DATA_DIR,
    GROUND_TRUTH_FIELDS,
    incident_path,
    list_incident_ids,
    load_evaluation_record,
    load_evidence_bundle,
    load_ground_truth,
    load_incident_context,
)
from .log_parser import classify_event, load_logs
from .metric_loader import load_metrics
from .models import (
    METRIC_FIELDS,
    NULLABLE_METRIC_FIELDS,
    EventType,
    IncidentContext,
    IncidentEvaluationRecord,
    IncidentEvidenceBundle,
    IncidentGroundTruth,
    LogEvent,
    LogLevel,
    MetricPoint,
    Severity,
)

__all__ = [
    # operational evidence: safe for investigation code
    "IncidentContext", "LogEvent", "MetricPoint", "IncidentEvidenceBundle", "EventType", "LogLevel", "Severity",
    "load_incident_context", "load_logs", "load_metrics", "load_evidence_bundle", "classify_event",
    # ground truth: evaluation only
    "IncidentGroundTruth", "IncidentEvaluationRecord", "load_ground_truth", "load_evaluation_record",
    # helpers
    "IngestionError", "RecordIssue", "CONTEXT_FIELDS", "GROUND_TRUTH_FIELDS", "METRIC_FIELDS",
    "NULLABLE_METRIC_FIELDS", "DEFAULT_DATA_DIR", "incident_path", "list_incident_ids",
]
