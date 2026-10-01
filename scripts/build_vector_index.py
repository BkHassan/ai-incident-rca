#!/usr/bin/env python3
"""Embed historical incidents and technical documents into local Chroma collections.

    python scripts/build_vector_index.py

Requires GEMINI_API_KEY or GOOGLE_API_KEY. The key is not written to disk.
Re-running replaces both collections. Embeddings are computed before the old
collections are deleted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from retrieval import (  # noqa: E402
    DEFAULT_EMBEDDING_MODEL,
    GeminiEmbeddingProvider,
    RetrievalError,
    build_index,
)
from retrieval.historical import historical_dir  # noqa: E402
from retrieval.indexer import default_vectorstore  # noqa: E402
from retrieval.technical import technical_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--vectorstore", type=Path, default=default_vectorstore(ROOT))
    parser.add_argument("--model", default=DEFAULT_EMBEDDING_MODEL)
    args = parser.parse_args()
    try:
        summary = build_index(
            GeminiEmbeddingProvider(model=args.model),
            vectorstore=args.vectorstore,
            historical_dir=historical_dir(ROOT),
            technical_dir=technical_dir(ROOT),
        )
    except RetrievalError as exc:
        print(f"Indexing failed: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Indexing failed: {exc.__class__.__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"Embedding model: {summary.embedding_model}")
    print(f"Historical incidents indexed: {summary.historical_count}")
    print(f"Technical document chunks indexed: {summary.technical_count}")
    print("Collections:")
    for name in summary.collections:
        print(f"  {name}")
    print(f"Vector store: {args.vectorstore}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
