"""Retrieval structure tests. Embeddings are a deterministic hash stand-in, not Gemini.

    python -m unittest tests.test_retrieval -v
"""

from __future__ import annotations

import ast
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion import incident_path, list_incident_ids, load_ground_truth  # noqa: E402
from retrieval import (  # noqa: E402
    HISTORICAL_COLLECTION,
    TECHNICAL_COLLECTION,
    HashEmbeddingProvider,
    RetrievalError,
    build_index,
    build_query_for_incident,
)
from retrieval.historical import historical_dir, load_historical_records, render_historical_text  # noqa: E402
from retrieval.indexer import open_store  # noqa: E402
from retrieval.query_builder import FORBIDDEN_QUERY  # noqa: E402
from retrieval.retriever import Retriever  # noqa: E402
from retrieval.technical import load_technical_chunks, technical_dir  # noqa: E402

DATA = ROOT / "data"
RETRIEVAL_SRC = ROOT / "src" / "retrieval"


def _index(path: Path):
    return build_index(
        HashEmbeddingProvider(),
        vectorstore=path,
        historical_dir=historical_dir(ROOT),
        technical_dir=technical_dir(ROOT),
    )


class QueryConstructionTests(unittest.TestCase):
    def test_query_uses_observed_evidence_and_not_labels(self):
        with patch("ingestion.incident_loader.load_ground_truth", side_effect=AssertionError("ground truth")):
            query = build_query_for_incident("INC-011", DATA)
        self.assertIn("payment-api", query)
        self.assertTrue(
            "latency" in query.lower() or "database connection" in query.lower() or "error" in query.lower(),
            query,
        )
        self.assertIsNone(FORBIDDEN_QUERY.search(query))
        self.assertNotIn("true_root_cause", query)
        self.assertNotIn("fault_start_time", query)
        self.assertNotIn("expected_symptoms", query)

    def test_every_current_incident_query_omits_evaluation_fields(self):
        for incident_id in list_incident_ids(DATA):
            with patch("ingestion.incident_loader.load_ground_truth", side_effect=AssertionError("ground truth")):
                query = build_query_for_incident(incident_id, DATA)
            self.assertIsNone(FORBIDDEN_QUERY.search(query), incident_id)
            truth = load_ground_truth(incident_path(incident_id, DATA))
            if truth.fault_start_time is not None:
                self.assertNotIn(truth.fault_start_time.isoformat(), query, incident_id)
            self.assertNotIn(truth.resolution, query, incident_id)
            for symptom in truth.expected_symptoms:
                if len(symptom) >= 40:
                    self.assertNotIn(symptom, query, incident_id)

    def test_normal_query_does_not_assert_a_failure_mode(self):
        query = build_query_for_incident("INC-014", DATA)
        self.assertIsNone(FORBIDDEN_QUERY.search(query))
        lowered = query.lower()
        self.assertTrue("anomaly" in lowered or "no metric" in lowered or "limited" in lowered)

    def test_retrieval_package_does_not_call_ground_truth_loaders(self):
        forbidden_calls = ("load_ground_truth", "load_evaluation_record")
        for path in RETRIEVAL_SRC.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
            for name in forbidden_calls:
                self.assertNotIn(name, names, path.name)


class IndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = Path(self.tmp.name)
        self.summary = _index(self.store)
        self.client = open_store(self.store)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def test_both_collections_exist_with_expected_counts(self):
        names = {collection.name for collection in self.client.list_collections()}
        self.assertEqual(names, {HISTORICAL_COLLECTION, TECHNICAL_COLLECTION})
        self.assertEqual(self.summary.historical_count, 30)
        self.assertEqual(self.client.get_collection(HISTORICAL_COLLECTION).count(), 30)
        self.assertGreaterEqual(self.summary.technical_count, 8)
        self.assertEqual(
            self.client.get_collection(TECHNICAL_COLLECTION).count(),
            self.summary.technical_count,
        )
        self.assertEqual(list(self.summary.historical_ids), [f"HIST-{i:03d}" for i in range(1, 31)])

    def test_technical_chunk_ids_are_stable_and_self_contained(self):
        first = load_technical_chunks(technical_dir(ROOT))
        second = load_technical_chunks(technical_dir(ROOT))
        self.assertEqual(first, second)
        ids = [chunk["id"] for chunk in first]
        self.assertEqual(ids, list(self.summary.technical_ids))
        self.assertIn("database_001", ids)
        self.assertIn("memory_001", ids)
        for chunk in first:
            self.assertGreaterEqual(len(chunk["text"]), 280)
            self.assertLessEqual(len(chunk["text"]), 4000)
            self.assertIn(chunk["metadata"]["section"], chunk["text"])
            self.assertEqual(chunk["metadata"]["source_type"], "technical_document")
            self.assertNotIn("INC-", chunk["text"])
            self.assertNotIn("DB_CONNECTION_POOL_EXHAUSTION", chunk["text"])

    def test_historical_text_keeps_root_cause_in_metadata_only(self):
        for record in load_historical_records(historical_dir(ROOT)):
            text = render_historical_text(record)
            self.assertNotIn(record["root_cause"], text)
        stored = self.client.get_collection(HISTORICAL_COLLECTION).get(include=["metadatas"])
        causes = {meta["historical_root_cause"] for meta in stored["metadatas"]}
        self.assertEqual(len(causes), 3)
        self.assertTrue(all(meta["source_type"] == "historical_incident" for meta in stored["metadatas"]))

    def test_rerun_keeps_ids_and_document_text(self):
        before = {
            name: self.client.get_collection(name).get(include=["documents", "metadatas"])
            for name in (HISTORICAL_COLLECTION, TECHNICAL_COLLECTION)
        }
        self.client.close()
        _index(self.store)
        client = open_store(self.store)
        self.client = client
        for name, snapshot in before.items():
            again = client.get_collection(name).get(include=["documents", "metadatas"])
            self.assertEqual(sorted(snapshot["ids"]), sorted(again["ids"]))
            by_id = dict(zip(snapshot["ids"], snapshot["documents"]))
            for doc_id, document in zip(again["ids"], again["documents"]):
                self.assertEqual(by_id[doc_id], document)

    def test_top_k_and_stable_ids(self):
        retriever = Retriever(self.store, HashEmbeddingProvider())
        self.client.close()
        try:
            query = build_query_for_incident("INC-011", DATA)
            first = retriever.retrieve(query, top_k=3)
            second = retriever.retrieve(query, top_k=3)
            self.assertLessEqual(len(first.historical_incidents), 3)
            self.assertLessEqual(len(first.technical_documents), 3)
            self.assertEqual(len(first.historical_incidents), 3)
            self.assertEqual(len(first.technical_documents), 3)
            self.assertEqual(
                [hit.incident_id for hit in first.historical_incidents],
                [hit.incident_id for hit in second.historical_incidents],
            )
            self.assertEqual(
                [hit.document_id for hit in first.technical_documents],
                [hit.document_id for hit in second.technical_documents],
            )
            self.assertEqual([hit.rank for hit in first.historical_incidents], [1, 2, 3])
            self.assertNotIn("true_root_cause", first.model_dump_json())
        finally:
            retriever.close()
            self.client = open_store(self.store)

    def test_empty_and_invalid_queries(self):
        retriever = Retriever(self.store, HashEmbeddingProvider())
        self.client.close()
        try:
            for bad in ("", "   ", None):
                with self.assertRaises(RetrievalError):
                    retriever.retrieve(bad, top_k=3)
            with self.assertRaises(RetrievalError):
                retriever.retrieve("payment-api latency increased", top_k=0)
        finally:
            retriever.close()
            self.client = open_store(self.store)


if __name__ == "__main__":
    unittest.main()
