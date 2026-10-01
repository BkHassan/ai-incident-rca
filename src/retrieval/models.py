"""Retrieval result models.

These objects describe retrieved historical incidents and technical passages.
They do not carry the current incident's evaluation label.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class RetrievalError(ValueError):
    """A retrieval request or index build cannot be completed."""


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class HistoricalIncidentResult(_Frozen):
    """One prior incident retrieved for an observational query."""

    rank: Annotated[int, Field(ge=1)]
    incident_id: str
    score: float  # cosine similarity, higher is closer; distance is also in metadata
    text: str
    metadata: dict[str, str | int | float | bool]


class TechnicalDocumentResult(_Frozen):
    """One technical-document chunk retrieved for an observational query."""

    rank: Annotated[int, Field(ge=1)]
    document_id: str
    section: str
    score: float
    text: str
    metadata: dict[str, str | int | float | bool]


class RetrievalResult(_Frozen):
    """Historical incidents and technical passages for one observational query."""

    query: str
    historical_incidents: tuple[HistoricalIncidentResult, ...]
    technical_documents: tuple[TechnicalDocumentResult, ...]


class IndexSummary(_Frozen):
    """What the indexer wrote. Ids and document text are compared across reruns; scores are not."""

    embedding_model: str
    historical_count: int
    technical_count: int
    historical_ids: tuple[str, ...]
    technical_ids: tuple[str, ...]
    collections: tuple[str, ...]
