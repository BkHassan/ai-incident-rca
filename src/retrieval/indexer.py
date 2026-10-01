"""Build or replace the two local Chroma collections."""

from __future__ import annotations

from pathlib import Path

from .embeddings import EmbeddingProvider
from .historical import historical_document, load_historical_records
from .models import IndexSummary, RetrievalError
from .technical import load_technical_chunks

HISTORICAL_COLLECTION = "historical_incidents"
TECHNICAL_COLLECTION = "technical_documents"
COLLECTIONS = (HISTORICAL_COLLECTION, TECHNICAL_COLLECTION)


def default_vectorstore(root: Path) -> Path:
    return root / "data" / "vectorstore"


def open_store(path: Path):
    import chromadb

    path.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(path))


def build_index(
    embedder: EmbeddingProvider,
    *,
    vectorstore: Path,
    historical_dir: Path,
    technical_dir: Path,
) -> IndexSummary:
    """Embed historical incidents and technical chunks, then replace both collections.

    Embeddings are computed before the collections are deleted, so a failed API call
    leaves an existing index in place.
    """
    records = load_historical_records(historical_dir)
    hist_rows = [historical_document(record) for record in records]
    tech_rows = load_technical_chunks(technical_dir)
    hist_vectors = embedder.embed_texts([text for _, text, _ in hist_rows], task="document")
    tech_vectors = embedder.embed_texts([row["text"] for row in tech_rows], task="document")
    if len(hist_vectors) != len(hist_rows) or len(tech_vectors) != len(tech_rows):
        raise RetrievalError("embedding count does not match document count")

    client = open_store(vectorstore)
    historical = _replace_collection(client, HISTORICAL_COLLECTION, embedder.model_name)
    technical = _replace_collection(client, TECHNICAL_COLLECTION, embedder.model_name)
    _add(historical, [doc_id for doc_id, _, _ in hist_rows],
         [text for _, text, _ in hist_rows],
         [meta for _, _, meta in hist_rows], hist_vectors)
    _add(technical, [row["id"] for row in tech_rows],
         [row["text"] for row in tech_rows],
         [row["metadata"] for row in tech_rows], tech_vectors)
    historical_count = historical.count()
    technical_count = technical.count()
    client.close()
    return IndexSummary(
        embedding_model=embedder.model_name,
        historical_count=historical_count,
        technical_count=technical_count,
        historical_ids=tuple(doc_id for doc_id, _, _ in hist_rows),
        technical_ids=tuple(row["id"] for row in tech_rows),
        collections=COLLECTIONS,
    )


def _replace_collection(client, name: str, model_name: str):
    existing = {collection.name for collection in client.list_collections()}
    if name in existing:
        client.delete_collection(name)
    return client.create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "embedding_model": model_name},
    )


def _add(collection, ids: list[str], documents: list[str], metadatas: list[dict], embeddings: list[list[float]]) -> None:
    if len({len(ids), len(documents), len(metadatas), len(embeddings)}) != 1:
        raise RetrievalError("index rows are not aligned")
    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)
