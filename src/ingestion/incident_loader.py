"""Load incident metadata and build evidence bundles.

Each ``raw/incidents/INC-XXX.json`` holds both what on-call sees and the answer. The loader
splits every file into two disjoint field sets:

* ``CONTEXT_FIELDS`` go into ``IncidentContext``, which investigation code may read.
* ``GROUND_TRUTH_FIELDS`` go into ``IncidentGroundTruth``, which only evaluation may read.

A field in neither set is rejected, so a new metadata field cannot reach an investigation
until someone decides which side it belongs to.

``load_evidence_bundle`` never reads ground-truth fields. Only ``load_ground_truth`` and
``load_evaluation_record`` do.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from .errors import IngestionError, RecordIssue, describe_validation_error
from .log_parser import load_logs
from .metric_loader import load_metrics
from .models import IncidentContext, IncidentEvaluationRecord, IncidentEvidenceBundle, IncidentGroundTruth

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "data"

CONTEXT_FIELDS = ("incident_id", "title", "service", "severity", "start_time", "end_time", "duration_minutes",
                  "window_start", "window_end", "description")
GROUND_TRUTH_FIELDS = ("incident_id", "scenario", "true_root_cause", "root_cause_service", "root_cause_variant",
                       "root_cause_detail", "fault_start_time", "expected_symptoms", "affected_services",
                       "resolution")
FILE_REFERENCE_FIELDS = ("evidence_files",)
_KNOWN_FIELDS = frozenset(CONTEXT_FIELDS + GROUND_TRUTH_FIELDS + FILE_REFERENCE_FIELDS)

Model = TypeVar("Model", bound=BaseModel)


def _read_metadata(path: Path) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IngestionError(path, [RecordIssue("file", f"invalid JSON ({exc.msg} at line {exc.lineno})")]) from exc
    if not isinstance(raw, dict):
        raise IngestionError(path, [RecordIssue("file", f"expected a JSON object, got {type(raw).__name__}")])
    iid = raw.get("incident_id") if isinstance(raw.get("incident_id"), str) else None
    issues = []
    unknown = sorted(set(raw) - _KNOWN_FIELDS)
    if unknown:
        issues.append(RecordIssue("fields", f"unrecognized fields {unknown}; classify them as context or "
                                            "ground truth in incident_loader before ingesting", iid))
    if iid is not None and iid != path.stem:
        issues.append(RecordIssue("field 'incident_id'", f"{iid!r} does not match file name {path.name!r}", iid))
    if issues:
        raise IngestionError(path, issues, iid)
    return raw


def _build(model: type[Model], raw: dict, fields: tuple[str, ...], path: Path) -> Model:
    try:
        return model.model_validate({name: raw[name] for name in fields if name in raw})
    except ValidationError as exc:
        iid = raw.get("incident_id") if isinstance(raw.get("incident_id"), str) else None
        raise IngestionError(path, [RecordIssue(model.__name__, describe_validation_error(exc), iid)], iid) from exc


def load_incident_context(path: str | Path) -> IncidentContext:
    """Load the operational context of one incident. No ground-truth field is read."""
    path = Path(path)
    return _build(IncidentContext, _read_metadata(path), CONTEXT_FIELDS, path)


def load_ground_truth(path: str | Path) -> IncidentGroundTruth:
    """Load the ground truth of one incident. Use it for evaluation only."""
    path = Path(path)
    return _build(IncidentGroundTruth, _read_metadata(path), GROUND_TRUTH_FIELDS, path)


def incident_path(incident_id: str, data_dir: str | Path = DEFAULT_DATA_DIR) -> Path:
    return Path(data_dir) / "raw" / "incidents" / f"{incident_id}.json"


def list_incident_ids(data_dir: str | Path = DEFAULT_DATA_DIR) -> list[str]:
    """Return the IDs of all incident metadata files, sorted."""
    return sorted(p.stem for p in (Path(data_dir) / "raw" / "incidents").glob("*.json"))


def _evidence_paths(raw: dict, path: Path, data_dir: Path) -> tuple[Path, Path]:
    files = raw.get("evidence_files")
    if not (isinstance(files, dict) and isinstance(files.get("logs"), str) and isinstance(files.get("metrics"), str)):
        raise IngestionError(path, [RecordIssue("field 'evidence_files'", "expected {'logs': str, 'metrics': str}",
                                                raw.get("incident_id"))])
    raw_dir = data_dir / "raw"
    return raw_dir / files["logs"], raw_dir / files["metrics"]


def load_evidence_bundle(incident_id: str, data_dir: str | Path = DEFAULT_DATA_DIR) -> IncidentEvidenceBundle:
    """Load exactly what an investigation may inspect: context, logs and metrics. No ground truth."""
    data_dir = Path(data_dir)
    path = incident_path(incident_id, data_dir)
    raw = _read_metadata(path)
    context = _build(IncidentContext, raw, CONTEXT_FIELDS, path)
    logs_path, metrics_path = _evidence_paths(raw, path, data_dir)
    logs = load_logs(logs_path, incident_id=context.incident_id)
    metrics = load_metrics(metrics_path, incident_id=context.incident_id)
    return IncidentEvidenceBundle(context=context, logs=tuple(logs), metrics=tuple(metrics))


def load_evaluation_record(incident_id: str, data_dir: str | Path = DEFAULT_DATA_DIR) -> IncidentEvaluationRecord:
    """Load an evidence bundle together with its ground truth, for evaluation."""
    evidence = load_evidence_bundle(incident_id, data_dir)
    ground_truth = load_ground_truth(incident_path(incident_id, data_dir))
    return IncidentEvaluationRecord(evidence=evidence, ground_truth=ground_truth)
