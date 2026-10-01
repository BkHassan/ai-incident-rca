"""Turn a historical postmortem into one searchable document.

The embedded text is observational postmortem prose. The confirmed historical root cause
stays in metadata and is not copied into the text.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import HistoricalIncidentResult, RetrievalError
from .scoring import ranked_query

SOURCE_TYPE = "historical_incident"


def historical_dir(root: Path) -> Path:
    return root / "knowledge" / "incidents"


def load_historical_records(directory: Path) -> list[dict]:
    paths = sorted(directory.glob("HIST-*.json"))
    if not paths:
        raise RetrievalError(f"no historical incidents in {directory}")
    records = []
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("incident_id") != path.stem:
            raise RetrievalError(f"{path.name} incident_id does not match the file name")
        records.append(record)
    return records


def historical_document(record: dict) -> tuple[str, str, dict[str, str | int | float | bool]]:
    """Return ``(document_id, text, metadata)`` for one postmortem."""
    incident_id = str(record["incident_id"])
    text = render_historical_text(record)
    if record.get("root_cause") and str(record["root_cause"]) in text:
        raise RetrievalError(f"{incident_id} root-cause label leaked into the indexed text")
    metadata: dict[str, str | int | float | bool] = {
        "incident_id": incident_id,
        "service": str(record.get("service", "")),
        "date": str(record.get("occurred_at", "")),
        "source_type": SOURCE_TYPE,
        "severity": str(record.get("severity", "")),
        "duration_minutes": int(record.get("duration_minutes") or 0),
    }
    if record.get("root_cause"):
        metadata["historical_root_cause"] = str(record["root_cause"])
    if record.get("root_cause_service"):
        metadata["historical_root_cause_service"] = str(record["root_cause_service"])
    return incident_id, text, metadata


def retrieve_similar_incidents(collection, embedder, query_text: str, top_k: int = 3) -> list[HistoricalIncidentResult]:
    hits = ranked_query(collection, embedder, query_text, top_k)
    results = []
    for rank, hit in enumerate(hits, start=1):
        metadata = hit["metadata"]
        results.append(HistoricalIncidentResult(
            rank=rank,
            incident_id=str(metadata.get("incident_id") or hit["id"]),
            score=hit["score"],
            text=hit["text"],
            metadata=metadata,
        ))
    return results


def render_historical_text(record: dict) -> str:
    """Postmortem text for embedding. Omits the structured root-cause label."""
    lines = [
        f"Incident {record['incident_id']}",
        f"Title: {record.get('title', '')}",
        f"Service: {record.get('service', '')}",
        f"Severity: {record.get('severity', '')}",
        f"Duration minutes: {record.get('duration_minutes', '')}",
        f"When: {record.get('occurred_at', '')}",
    ]
    affected = record.get("affected_services") or []
    if affected:
        lines.append("Affected services: " + ", ".join(str(name) for name in affected))
    lines.append("Symptoms:")
    lines.extend(f"- {item}" for item in record.get("symptoms") or [])
    lines.append("Observed signals:")
    lines.extend(f"- {item}" for item in record.get("observed_signals") or [])
    lines.append("Timeline:")
    for step in record.get("timeline") or []:
        lines.append(f"- {step.get('relative_time', '')}: {step.get('event', '')}")
    lines.append("Contributing factors:")
    lines.extend(f"- {item}" for item in record.get("contributing_factors") or [])
    lines.append("Resolution:")
    lines.extend(f"- {item}" for item in record.get("resolution") or [])
    lines.append("Lessons learned:")
    lines.extend(f"- {item}" for item in record.get("lessons_learned") or [])
    tags = record.get("tags") or []
    if tags:
        lines.append("Tags: " + ", ".join(str(tag) for tag in tags))
    return "\n".join(lines).strip() + "\n"
