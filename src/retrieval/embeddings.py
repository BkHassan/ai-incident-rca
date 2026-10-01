"""Text embeddings for the retrieval index.

The production provider calls the current Google GenAI SDK:

    client.models.embed_content(..., config=EmbedContentConfig(...))

``gemini-embedding-001`` is the default. It is the supported text embedding model whose
``EmbedContentConfig.task_type`` distinguishes ``RETRIEVAL_DOCUMENT`` from ``RETRIEVAL_QUERY``,
and a list of inputs returns one vector per text. ``gemini-embedding-2`` is selected with
``EMBEDDING_MODEL``. That model does not accept ``task_type``; retrieval instructions are
prefixed into the text, and each input is embedded separately because a list is aggregated
into one vector.

``HashEmbeddingProvider`` is a deterministic stand-in for tests. It is not a semantic model
and must not be written to the project vector store as if it were Gemini.
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import Protocol

from .models import RetrievalError

DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_DIMENSIONS = 768
_BATCH_SIZE = 16


class EmbeddingProvider(Protocol):
    model_name: str

    def embed_text(self, text: str, *, task: str = "document") -> list[float]: ...

    def embed_texts(self, texts: list[str], *, task: str = "document") -> list[list[float]]: ...


def _normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in values))
    if norm == 0.0:
        raise RetrievalError("embedding norm is zero")
    return [value / norm for value in values]


def _require_texts(texts: list[str]) -> None:
    if any(not isinstance(text, str) or not text.strip() for text in texts):
        raise RetrievalError("cannot embed empty text")


class GeminiEmbeddingProvider:
    """Gemini embeddings through ``client.models.embed_content``.

    The API key is read from ``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``. The model name and
    output size can be changed with ``EMBEDDING_MODEL`` and ``EMBEDDING_DIMENSIONS`` without
    changing retrieval code.
    """

    def __init__(
        self,
        model: str | None = None,
        dimensions: int | None = None,
        api_key: str | None = None,
        client=None,
    ) -> None:
        self.model_name = model or os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)
        raw_dim = os.environ.get("EMBEDDING_DIMENSIONS")
        self.dimensions = int(raw_dim) if raw_dim else (dimensions or DEFAULT_DIMENSIONS)
        if self.dimensions < 1:
            raise RetrievalError("embedding dimensions must be positive")
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        self._client = client

    @property
    def uses_task_type(self) -> bool:
        """``gemini-embedding-001`` takes task_type. ``gemini-embedding-2`` does not."""
        return "embedding-2" not in self.model_name

    def embed_text(self, text: str, *, task: str = "document") -> list[float]:
        return self.embed_texts([text], task=task)[0]

    def embed_texts(self, texts: list[str], *, task: str = "document") -> list[list[float]]:
        _require_texts(texts)
        if not texts:
            return []
        _check_task(task)
        if self.uses_task_type:
            return self._embed_batched(texts, task)
        return [self._embed_one(self._prefix_embedding2(text, task), task_type=None) for text in texts]

    def _prefix_embedding2(self, text: str, task: str) -> str:
        if task == "query":
            return f"task: search result | query: {text}"
        return f"title: none | text: {text}"

    def _embed_batched(self, texts: list[str], task: str) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _BATCH_SIZE):
            batch = texts[start:start + _BATCH_SIZE]
            vectors.extend(self._embed_contents(batch, task))
        if len(vectors) != len(texts):
            raise RetrievalError(f"embedding API returned {len(vectors)} vectors for {len(texts)} texts")
        return vectors

    def _embed_contents(self, texts: list[str], task: str) -> list[list[float]]:
        # A one-item list is sent as a string so the SDK returns one embedding, not an aggregate.
        contents: str | list[str] = texts[0] if len(texts) == 1 else texts
        response = self._client_or_create().models.embed_content(
            model=self.model_name,
            contents=contents,
            config=self._config(task),
        )
        embeddings = list(response.embeddings or [])
        if len(embeddings) != len(texts):
            raise RetrievalError(
                f"embedding API returned {len(embeddings)} vectors for {len(texts)} texts"
            )
        return [_normalize(list(item.values)) for item in embeddings]

    def _embed_one(self, text: str, task_type: str | None) -> list[float]:
        response = self._client_or_create().models.embed_content(
            model=self.model_name,
            contents=text,
            config=self._config_for_type(task_type),
        )
        embeddings = list(response.embeddings or [])
        if len(embeddings) != 1:
            raise RetrievalError(f"expected 1 embedding, got {len(embeddings)}")
        return _normalize(list(embeddings[0].values))

    def _config(self, task: str):
        task_type = "RETRIEVAL_DOCUMENT" if task == "document" else "RETRIEVAL_QUERY"
        return self._config_for_type(task_type)

    def _config_for_type(self, task_type: str | None):
        from google.genai import types

        kwargs = {"output_dimensionality": self.dimensions}
        if task_type is not None:
            kwargs["task_type"] = task_type
        return types.EmbedContentConfig(**kwargs)

    def _client_or_create(self):
        if self._client is not None:
            return self._client
        if not self._api_key:
            raise RetrievalError(
                "Set GEMINI_API_KEY or GOOGLE_API_KEY before embedding. Do not commit the key."
            )
        from google import genai

        self._client = genai.Client(api_key=self._api_key)
        return self._client


class HashEmbeddingProvider:
    """Deterministic bag-of-tokens vectors for tests. Not a substitute for Gemini."""

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions < 8:
            raise RetrievalError("hash embedding dimensions must be at least 8")
        self.model_name = f"hash-{dimensions}"
        self.dimensions = dimensions

    def embed_text(self, text: str, *, task: str = "document") -> list[float]:
        return self.embed_texts([text], task=task)[0]

    def embed_texts(self, texts: list[str], *, task: str = "document") -> list[list[float]]:
        _require_texts(texts)
        _check_task(task)
        # ``task`` is ignored so a query and a document that share words land in one space.
        return [_embed_tokens(text, self.dimensions) for text in texts]


def _check_task(task: str) -> None:
    if task not in ("document", "query"):
        raise RetrievalError(f"embedding task must be 'document' or 'query', got {task!r}")


def _embed_tokens(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    tokens = [tok for tok in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split() if tok]
    if not tokens:
        raise RetrievalError("cannot embed text with no tokens")
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for offset in range(4):
            slot = digest[offset] % dimensions
            sign = 1.0 if digest[offset + 4] % 2 == 0 else -1.0
            vector[slot] += sign
    return _normalize(vector)
