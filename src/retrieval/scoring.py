"""Shared Chroma query ranking. Higher score means closer (cosine similarity)."""

from __future__ import annotations

from .models import RetrievalError


def require_query(query_text: str) -> str:
    if not isinstance(query_text, str) or not query_text.strip():
        raise RetrievalError("retrieval query must be a non-empty string")
    return query_text.strip()


def ranked_query(collection, embedder, query_text: str, top_k: int) -> list[dict]:
    query_text = require_query(query_text)
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise RetrievalError("top_k must be an integer >= 1")
    available = collection.count()
    n_results = min(top_k, available)
    if n_results == 0:
        return []
    vector = embedder.embed_text(query_text, task="query")
    raw = collection.query(
        query_embeddings=[vector],
        n_results=n_results,
        include=["documents", "metadatas", "distances"],
    )
    ids = raw["ids"][0]
    documents = raw["documents"][0]
    metadatas = raw["metadatas"][0]
    distances = raw["distances"][0]
    hits = []
    for doc_id, document, metadata, distance in zip(ids, documents, metadatas, distances):
        meta = dict(metadata or {})
        distance_value = float(distance)
        meta["distance"] = distance_value
        hits.append({
            "id": doc_id,
            "text": document or "",
            "score": 1.0 - distance_value,
            "metadata": _plain_metadata(meta),
        })
    return hits


def _plain_metadata(metadata: dict) -> dict[str, str | int | float | bool]:
    plain: dict[str, str | int | float | bool] = {}
    for key, value in metadata.items():
        if isinstance(value, bool | int | float | str):
            plain[str(key)] = value
        elif value is None:
            continue
        else:
            plain[str(key)] = str(value)
    return plain
