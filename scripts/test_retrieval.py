#!/usr/bin/env python3
"""Retrieve similar history and technical passages for representative incidents.

    python scripts/test_retrieval.py

Uses the local Chroma store built by scripts/build_vector_index.py.
Prints observational queries and the top 3 hits. It does not score root-cause accuracy.
The evaluation label is printed only after retrieval, from the incident index, so it can
be compared by eye. It is not part of the query.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retrieval import GeminiEmbeddingProvider, RetrievalError, Retriever, build_query_for_incident  # noqa: E402
from retrieval.indexer import default_vectorstore  # noqa: E402

DATA = ROOT / "data"
# Representative cases. These labels are section headers only; they are not retrieval input.
CASES = (
    ("INC-011", "database-connection pattern"),
    ("INC-010", "memory-growth pattern"),
    ("INC-002", "downstream-latency pattern"),
    ("INC-014", "normal operations"),
)


def evaluation_labels() -> dict[str, str]:
    path = DATA / "generated" / "incidents_index.csv"
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["incident_id"]: row["scenario"] for row in csv.DictReader(handle)}


def main() -> int:
    store = default_vectorstore(ROOT)
    if not store.exists():
        print(f"No vector store at {store}. Run scripts/build_vector_index.py first.", file=sys.stderr)
        return 1
    try:
        retriever = Retriever(store, GeminiEmbeddingProvider())
    except RetrievalError as exc:
        print(f"Retrieval failed: {exc}", file=sys.stderr)
        return 1
    labels = evaluation_labels()
    try:
        for incident_id, heading in CASES:
            query = build_query_for_incident(incident_id, DATA)
            result = retriever.retrieve(query, top_k=3)
            print("=" * 72)
            print(f"{incident_id}  ({heading})")
            print("-" * 72)
            print(query)
            print()
            print("Historical incidents:")
            for hit in result.historical_incidents:
                cause = hit.metadata.get("historical_root_cause", "")
                print(f"  {hit.rank}. {hit.incident_id}  score={hit.score:.3f}  "
                      f"service={hit.metadata.get('service')}  prior={cause}")
            print("Technical documents:")
            for hit in result.technical_documents:
                print(f"  {hit.rank}. {hit.document_id}  score={hit.score:.3f}  section={hit.section}")
            print()
            print(f"Evaluation label (not used in the query): {labels.get(incident_id, '')}")
            print()
    except RetrievalError as exc:
        print(f"Retrieval failed: {exc}", file=sys.stderr)
        return 1
    finally:
        retriever.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
