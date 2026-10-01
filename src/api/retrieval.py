"""Read-only projection of an existing RetrievalResult.

Scoring and Chroma access stay in ``retrieval``. This module only copies fields
the retriever already returned.
"""

from __future__ import annotations

from retrieval.models import HistoricalIncidentResult, RetrievalResult, TechnicalDocumentResult

from .schemas import HistoricalHit, RetrievalResponse, TechnicalHit


def project_retrieval(incident_id: str, result: RetrievalResult) -> RetrievalResponse:
    return RetrievalResponse(
        incident_id=incident_id,
        query=result.query,
        historical_incidents=[_historical(item) for item in result.historical_incidents],
        technical_documents=[_technical(item) for item in result.technical_documents],
    )


def _historical(item: HistoricalIncidentResult) -> HistoricalHit:
    metadata = item.metadata
    duration = metadata.get("duration_minutes")
    return HistoricalHit(
        rank=item.rank,
        incident_id=item.incident_id,
        score=item.score,
        text=item.text,
        service=_text(metadata, "service"),
        occurred_at=_text(metadata, "date"),
        severity=_text(metadata, "severity"),
        duration_minutes=int(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None,
        historical_root_cause=_text(metadata, "historical_root_cause"),
        historical_root_cause_service=_text(metadata, "historical_root_cause_service"),
    )


def _technical(item: TechnicalDocumentResult) -> TechnicalHit:
    return TechnicalHit(
        rank=item.rank,
        document_id=item.document_id,
        title=_document_title(item.text, item.metadata),
        section=item.section,
        score=item.score,
        text=item.text,
        document_name=_text(item.metadata, "document_name"),
    )


def _document_title(text: str, metadata: dict) -> str:
    for line in text.splitlines():
        if line.startswith("Document: "):
            title = line.removeprefix("Document: ").strip()
            if title:
                return title
    name = _text(metadata, "document_name")
    if name:
        return name.removesuffix(".md")
    return str(metadata.get("document_id") or "")


def _text(metadata: dict, key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None
