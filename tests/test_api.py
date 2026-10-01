"""API tests. They use a fake investigator and do not call Gemini.

    python -m unittest tests.test_api -v
"""

from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi.testclient import TestClient  # noqa: E402

from api.main import create_app  # noqa: E402
from investigation import (  # noqa: E402
    InvestigationFailed,
    InvestigationService,
    RCAResult,
    Settings,
    VectorStoreMissing,
)
from investigation.models import RecommendedAction, RootCauseHypothesis  # noqa: E402
from retrieval.models import HistoricalIncidentResult, RetrievalResult, TechnicalDocumentResult  # noqa: E402

DATA = ROOT / "data"


def _result() -> RCAResult:
    cause = RootCauseHypothesis(
        cause="callers waited on a dependency",
        confidence=0.61,
        supporting_evidence_ids=["LOG-000001"],
        contradicting_evidence_ids=[],
        rationale="Timeouts were observed on the alerting service.",
    )
    return RCAResult(
        incident_id="INC-011",
        summary="The alert coincides with dependency timeouts.",
        root_cause=cause,
        confidence=0.61,
        alternative_causes=[],
        supporting_evidence=[],
        contradicting_evidence=[],
        timeline=[],
        recommended_actions=[RecommendedAction(
            action="Compare dependency latency with caller CPU.",
            rationale="The timeout log is the cited observation.",
            evidence_ids=["LOG-000001"],
        )],
        similar_incidents=[],
    )


class _Retriever:
    def retrieve_incident(self, incident_id, data_dir, top_k=3):
        return RetrievalResult(
            query="observational query",
            historical_incidents=(HistoricalIncidentResult(
                rank=1, incident_id="HIST-001", score=0.5,
                text="latency and timeouts",
                metadata={"incident_id": "HIST-001", "service": "payment-api", "date": "2024-04-06",
                          "source_type": "historical_incident", "severity": "LOW", "duration_minutes": 16},
            ),),
            technical_documents=(TechnicalDocumentResult(
                rank=1, document_id="networking_001", section="Downstream latency", score=0.5,
                text="downstream latency is time spent off-box",
                metadata={"document_id": "networking_001", "document_name": "networking.md",
                          "section": "Downstream latency", "source_type": "technical_document"},
            ),),
        )


class _Investigator:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    def investigate(self, context):
        if self.error:
            raise self.error
        return self.result.model_copy(update={"incident_id": context.incident_id})


def _service(investigator) -> InvestigationService:
    return InvestigationService(
        Settings(api_key="test-not-a-real-key"),
        investigator,
        _Retriever(),
        DATA,
    )


class ApiTests(unittest.TestCase):
    def test_mocked_success_matches_schema(self):
        app = create_app(service=_service(_Investigator(result=_result())))
        response = TestClient(app).post(
            "/api/incidents/investigate", json={"incident_id": "INC-011"})
        self.assertEqual(response.status_code, 200, response.text)
        parsed = RCAResult.model_validate(response.json())
        self.assertEqual(parsed.incident_id, "INC-011")
        self.assertEqual(parsed.root_cause.cause, "callers waited on a dependency")
        self.assertIsInstance(parsed.confidence, float)
        self.assertEqual(parsed.root_cause.supporting_evidence_ids, ["LOG-000001"])

    def test_second_valid_incident(self):
        app = create_app(service=_service(_Investigator(result=_result())))
        response = TestClient(app).post(
            "/api/incidents/investigate", json={"incident_id": "INC-010"})
        self.assertEqual(response.status_code, 200, response.text)
        parsed = RCAResult.model_validate(response.json())
        self.assertEqual(parsed.incident_id, "INC-010")

    def test_unknown_incident(self):
        app = create_app(service=_service(_Investigator(result=_result())))
        response = TestClient(app).post(
            "/api/incidents/investigate", json={"incident_id": "INC-099"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "not_found")

    def test_malformed_request(self):
        app = create_app(service=_service(_Investigator(result=_result())))
        client = TestClient(app)
        missing = client.post("/api/incidents/investigate", json={})
        self.assertEqual(missing.status_code, 422)
        bad = client.post("/api/incidents/investigate", json={"incident_id": "INC-0012"})
        self.assertEqual(bad.status_code, 422)

    def test_missing_configuration(self):
        removed = {}
        for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
            if name in os.environ:
                removed[name] = os.environ.pop(name)
        try:
            app = create_app(load_env=False)
            response = TestClient(app).post(
                "/api/incidents/investigate", json={"incident_id": "INC-011"})
        finally:
            os.environ.update(removed)
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["error"], "configuration_error")
        self.assertNotIn("AIza", response.text)
        self.assertNotRegex(response.text, r"sk-[A-Za-z0-9]")
        self.assertNotRegex(response.text, r"AQ\.[A-Za-z0-9_\-]+")

    def test_missing_vector_store(self):
        from unittest.mock import patch

        app = create_app(load_env=False)
        with patch(
            "investigation.build_default_service",
            side_effect=VectorStoreMissing("Chroma store not found. Run scripts/build_vector_index.py."),
        ):
            response = TestClient(app).post(
                "/api/incidents/investigate", json={"incident_id": "INC-011"})
        self.assertEqual(response.status_code, 503)
        body = response.json()
        self.assertEqual(body["error"], "vector_store_missing")
        self.assertNotRegex(response.text, r"AQ\.[A-Za-z0-9_\-]+")
        self.assertNotIn("AIza", response.text)

    def test_mocked_investigation_failure(self):
        app = create_app(service=_service(_Investigator(
            error=InvestigationFailed("the model request failed"))))
        response = TestClient(app).post(
            "/api/incidents/investigate", json={"incident_id": "INC-011"})
        self.assertEqual(response.status_code, 502)
        self.assertEqual(response.json()["error"], "investigation_failed")
        self.assertIn("model request failed", response.json()["detail"])
        self.assertNotRegex(response.text, r"AQ\.[A-Za-z0-9_\-]+")


class CatalogApiTests(unittest.TestCase):
    def test_list_uses_context_fields_only(self):
        response = TestClient(create_app(load_env=False)).get("/api/incidents")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertGreaterEqual(len(body["incidents"]), 35)
        incident = next(item for item in body["incidents"] if item["incident_id"] == "INC-011")
        self.assertEqual(incident["service"], "payment-api")
        self.assertEqual(incident["severity"], "HIGH")
        self.assertEqual(incident["title"], "payment-api error-rate SLO burn")
        self.assertNotIn("scenario", incident)
        self._assert_no_ground_truth(response.text)

    def test_detail_separates_metadata_and_evidence(self):
        response = TestClient(create_app(load_env=False)).get("/api/incidents/INC-011")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["incident_id"], "INC-011")
        self.assertIn("description", body)
        self.assertGreater(body["logs"]["line_count"], 0)
        self.assertTrue(body["anomalies_available"])
        self.assertGreater(len(body["anomaly_windows"]), 0)
        self.assertTrue(body["timeline_available"])
        self.assertGreater(len(body["timeline"]), 0)
        self.assertNotIn("description", body["timeline"][0])
        self.assertNotIn("points", body)
        self._assert_no_ground_truth(response.text)

    def test_timeline_matches_derived_evidence(self):
        response = TestClient(create_app(load_env=False)).get("/api/incidents/INC-011")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        derived = json.loads((DATA / "derived" / "correlation" / "INC-011.json").read_text(encoding="utf-8"))
        backend = {item["evidence_id"]: item for item in derived["evidence_items"]}
        returned = body["timeline"]
        self.assertGreater(len(returned), 0)
        self.assertLess(len(returned), body["logs"]["line_count"])
        types = {item["evidence_type"] for item in returned}
        self.assertIn("ANOMALY", types)
        self.assertIn("ANOMALY_WINDOW", types)
        self.assertTrue(types & {"LOG_EVENT", "ERROR_EVENT", "TIMEOUT_EVENT", "HEALTH_EVENT"})
        for item in returned:
            match = backend[item["evidence_id"]]
            self.assertEqual(item["summary"], match["summary"])
            self.assertEqual(item["service"], match["service"])
            self.assertEqual(item["evidence_type"], match["evidence_type"])
        self.assertGreater(len(body["anomaly_windows"]), 0)
        self.assertLess(len(body["anomaly_windows"]), 50)
        self.assertGreater(len(body["anomaly_metrics"]), 0)
        for metric in body["anomaly_metrics"]:
            self.assertGreater(metric["point_count"] + metric["window_count"], 0)
            self.assertTrue(metric["label"])

    def test_unknown_catalog_incident(self):
        response = TestClient(create_app(load_env=False)).get("/api/incidents/INC-099")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"], "not_found")

    def test_malformed_catalog_incident(self):
        response = TestClient(create_app(load_env=False)).get("/api/incidents/not-an-id")
        self.assertEqual(response.status_code, 422)

    def _assert_no_ground_truth(self, text: str):
        from ingestion import incident_path, load_ground_truth

        truth = load_ground_truth(incident_path("INC-011", DATA))
        for key in (
            "scenario", "true_root_cause", "root_cause_service", "root_cause_variant",
            "root_cause_detail", "fault_start_time", "expected_symptoms", "affected_services",
            "resolution",
        ):
            self.assertNotRegex(text, rf'"{key}"\s*:')
        self.assertNotIn(truth.root_cause_detail, text)
        self.assertNotIn(truth.resolution, text)
        self.assertNotIn(truth.scenario, text)
        self.assertNotIn(truth.root_cause_variant, text)
        for symptom in truth.expected_symptoms:
            self.assertNotIn(symptom, text)


if __name__ == "__main__":
    unittest.main()
