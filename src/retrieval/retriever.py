"""Unified retrieval over historical incidents and technical documents."""

from __future__ import annotations

from pathlib import Path

from .historical import retrieve_similar_incidents
from .indexer import HISTORICAL_COLLECTION, TECHNICAL_COLLECTION, open_store
from .models import RetrievalResult
from .query_builder import build_query_for_incident
from .technical import retrieve_technical_documents


class Retriever:
    """Search both Chroma collections. Does not call a generative model."""

    def __init__(self, store_path: Path, embedder) -> None:
        client = open_store(store_path)
        self._client = client
        self.embedder = embedder
        self.historical = client.get_collection(HISTORICAL_COLLECTION)
        self.technical = client.get_collection(TECHNICAL_COLLECTION)

    def close(self) -> None:
        self._client.close()

    def retrieve(self, query_text: str, top_k: int = 3) -> RetrievalResult:
        historical = tuple(retrieve_similar_incidents(
            self.historical, self.embedder, query_text, top_k))
        technical = tuple(retrieve_technical_documents(
            self.technical, self.embedder, query_text, top_k))
        return RetrievalResult(
            query=query_text.strip(),
            historical_incidents=historical,
            technical_documents=technical,
        )

    def retrieve_incident(self, incident_id: str, data_dir: Path, top_k: int = 3) -> RetrievalResult:
        query = build_query_for_incident(incident_id, data_dir)
        return self.retrieve(query, top_k=top_k)


def retrieve_for_incident(incident_id: str, store_path: Path, embedder, data_dir: Path, top_k: int = 3) -> RetrievalResult:
    return Retriever(store_path, embedder).retrieve_incident(incident_id, data_dir, top_k=top_k)
