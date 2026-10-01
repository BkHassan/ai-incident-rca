"""Build a compact investigation context from observed evidence and retrieval hits.

The builder reads incident context, anomaly output, and the observational timeline.
It does not read evaluation fields.
"""

from __future__ import annotations

from pathlib import Path

from correlation.models import EvidenceItem, IncidentTimeline, SourceType
from detection.models import IncidentAnomalyReport
from ingestion import DEFAULT_DATA_DIR, incident_path, load_incident_context
from retrieval.models import HistoricalIncidentResult, RetrievalResult, TechnicalDocumentResult

from .models import CitedEvidence, EvidenceSource, InvestigationContext

_SOURCE = {
    SourceType.LOG: EvidenceSource.LOG,
    SourceType.METRIC_ANOMALY: EvidenceSource.METRIC_ANOMALY,
    SourceType.ANOMALY_WINDOW: EvidenceSource.ANOMALY_WINDOW,
}
_DETAIL_LIMIT = 500


def build_investigation_context(
    incident_id: str,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    retrieval: RetrievalResult | None = None,
) -> InvestigationContext:
    """Combine operational context, timelines, and retrieval hits.

    ``retrieval`` is required so this function never opens the vector store itself
    and never reads an evaluation record. Pass the Day 8 retrieval result.
    """
    if retrieval is None:
        raise ValueError("retrieval result is required")
    data_dir = Path(data_dir)
    context = load_incident_context(incident_path(incident_id, data_dir))
    if context.incident_id != incident_id:
        raise ValueError(f"context id {context.incident_id} does not match {incident_id}")
    anomalies = IncidentAnomalyReport.model_validate_json(
        (data_dir / "derived" / "anomalies" / f"{incident_id}.json").read_text(encoding="utf-8"))
    timeline = IncidentTimeline.model_validate_json(
        (data_dir / "derived" / "correlation" / f"{incident_id}.json").read_text(encoding="utf-8"))
    if anomalies.incident_id != incident_id or timeline.incident_id != incident_id:
        raise ValueError("derived artifacts do not match the requested incident")

    evidence = [_from_timeline_item(item) for item in _ordered_items(timeline)]
    evidence.extend(_from_historical(hit) for hit in retrieval.historical_incidents)
    evidence.extend(_from_technical(hit) for hit in retrieval.technical_documents)
    evidence.sort(key=lambda item: item.evidence_id)
    return InvestigationContext(
        incident_id=context.incident_id,
        service=context.service,
        severity=context.severity.value,
        title=context.title,
        description=context.description,
        alert_start=context.start_time.isoformat(),
        alert_end=context.end_time.isoformat(),
        duration_minutes=context.duration_minutes,
        involved_services=list(timeline.involved_services),
        retrieval_query=retrieval.query,
        evidence=evidence,
    )


def _ordered_items(timeline: IncidentTimeline) -> list[EvidenceItem]:
    return sorted(timeline.evidence_items, key=lambda item: (item.timestamp, item.evidence_id))


def _from_timeline_item(item: EvidenceItem) -> CitedEvidence:
    text = " ".join(item.summary.split())
    return CitedEvidence(
        evidence_id=item.evidence_id,
        source_type=_SOURCE[item.source_type],
        short_description=_clip(text, 240),
        detail=_clip(text, _DETAIL_LIMIT),
        timestamp=item.timestamp.isoformat(),
    )


def _from_historical(hit: HistoricalIncidentResult) -> CitedEvidence:
    # Observational postmortem text only. The prior cause label is not copied in.
    body = " ".join(hit.text.split())
    detail = f"Retrieved prior incident {hit.incident_id} (similarity {hit.score:.3f}). {body}"
    return CitedEvidence(
        evidence_id=hit.incident_id,
        source_type=EvidenceSource.HISTORICAL_INCIDENT,
        short_description=_clip(detail, 240),
        detail=_clip(detail, _DETAIL_LIMIT),
        timestamp=str(hit.metadata.get("date", "")),
    )


def _from_technical(hit: TechnicalDocumentResult) -> CitedEvidence:
    body = " ".join(hit.text.split())
    detail = (f"Technical note {hit.document_id}, section {hit.section} "
              f"(similarity {hit.score:.3f}). {body}")
    return CitedEvidence(
        evidence_id=hit.document_id,
        source_type=EvidenceSource.TECHNICAL_DOCUMENT,
        short_description=_clip(detail, 240),
        detail=_clip(detail, _DETAIL_LIMIT),
    )


def _clip(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."
