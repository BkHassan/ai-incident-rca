"""Retrieval of similar historical incidents and relevant technical passages.

    from retrieval import Retriever, build_query_for_incident

The query is built from observed evidence only. This package does not rank root causes
and does not call a generative model.
"""

from .embeddings import (
    DEFAULT_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    GeminiEmbeddingProvider,
    HashEmbeddingProvider,
)
from .historical import retrieve_similar_incidents
from .indexer import HISTORICAL_COLLECTION, TECHNICAL_COLLECTION, build_index
from .models import (
    HistoricalIncidentResult,
    IndexSummary,
    RetrievalError,
    RetrievalResult,
    TechnicalDocumentResult,
)
from .query_builder import build_query_for_incident, build_retrieval_query
from .retriever import Retriever, retrieve_for_incident
from .technical import retrieve_technical_documents

__all__ = [
    "Retriever", "retrieve_for_incident", "build_index", "build_retrieval_query", "build_query_for_incident",
    "retrieve_similar_incidents", "retrieve_technical_documents",
    "GeminiEmbeddingProvider", "HashEmbeddingProvider",
    "DEFAULT_EMBEDDING_MODEL", "DEFAULT_DIMENSIONS",
    "RetrievalResult", "HistoricalIncidentResult", "TechnicalDocumentResult", "IndexSummary", "RetrievalError",
    "HISTORICAL_COLLECTION", "TECHNICAL_COLLECTION",
]
