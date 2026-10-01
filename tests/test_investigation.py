"""Unit tests for the RCA schema, context, prompt, and evidence guardrails.

    python -m unittest tests.test_investigation -v

No live Gemini calls.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion import incident_path, load_ground_truth  # noqa: E402
from investigation import (  # noqa: E402
    INSUFFICIENT_EVIDENCE,
    GeminiInvestigator,
    InvalidRCA,
    Settings,
    build_investigation_context,
    render_prompt,
    validate_rca,
)
from investigation.evidence import insufficient_result  # noqa: E402
from investigation.investigator import _public_message  # noqa: E402
from investigation.models import (  # noqa: E402
    CitedEvidence,
    EvidenceReference,
    EvidenceSource,
    InvestigationContext,
    RCAResult,
    RecommendedAction,
    RootCauseHypothesis,
    SimilarIncident,
    TimelineEntry,
)
from pydantic import ValidationError  # noqa: E402
from retrieval.models import HistoricalIncidentResult, RetrievalResult, TechnicalDocumentResult  # noqa: E402

DATA = ROOT / "data"


def _retrieval() -> RetrievalResult:
    return RetrievalResult(
        query="payment-api latency and database connection waits",
        historical_incidents=(HistoricalIncidentResult(
            rank=1,
            incident_id="HIST-007",
            score=0.81,
            text="Title: inventory waits\nSymptoms:\n- connection waits\n- elevated latency",
            metadata={
                "incident_id": "HIST-007",
                "service": "inventory-service",
                "date": "2024-08-09T20:41:09",
                "source_type": "historical_incident",
                "severity": "MEDIUM",
                "duration_minutes": 44,
            },
        ),),
        technical_documents=(TechnicalDocumentResult(
            rank=1,
            document_id="database_003",
            section="Acquisition timeouts",
            score=0.74,
            text="Document: pools\nSection: Acquisition timeouts\n\nAcquire timeouts fire before a query is sent.",
            metadata={
                "document_id": "database_003",
                "document_name": "database.md",
                "section": "Acquisition timeouts",
                "source_type": "technical_document",
            },
        ),),
    )


def _context(incident_id: str = "INC-011") -> InvestigationContext:
    return build_investigation_context(incident_id, DATA, _retrieval())


def _hypothesis(cause: str, evidence_id: str, confidence: float = 0.7) -> RootCauseHypothesis:
    return RootCauseHypothesis(
        cause=cause,
        confidence=confidence,
        supporting_evidence_ids=[evidence_id],
        contradicting_evidence_ids=[],
        rationale="The cited observation matches this hypothesis.",
    )


class SchemaTests(unittest.TestCase):
    def test_valid_rca(self):
        cause = _hypothesis("connection acquisition delays", "LOG-000001", 0.72)
        result = RCAResult(
            incident_id="INC-011",
            summary="Requests waited while borrowing database connections.",
            root_cause=cause,
            confidence=0.72,
            alternative_causes=[],
            supporting_evidence=[EvidenceReference(
                evidence_id="LOG-000001",
                source_type=EvidenceSource.LOG,
                short_description="connection wait",
            )],
            contradicting_evidence=[],
            timeline=[TimelineEntry(evidence_id="LOG-000001", description="connection wait")],
            recommended_actions=[RecommendedAction(
                action="Inspect pool wait metrics.",
                rationale="The wait logs are the strongest observation.",
                evidence_ids=["LOG-000001"],
            )],
            similar_incidents=[],
        )
        self.assertEqual(result.root_cause.cause, "connection acquisition delays")

    def test_invalid_confidence_is_rejected(self):
        with self.assertRaises(ValidationError):
            RootCauseHypothesis(
                cause="something",
                confidence=1.5,
                supporting_evidence_ids=["LOG-000001"],
                rationale="too sure",
            )

    def test_cause_without_evidence_is_rejected(self):
        cause = RootCauseHypothesis(
            cause="something",
            confidence=0.4,
            supporting_evidence_ids=[],
            rationale="no citations",
        )
        with self.assertRaises(ValidationError):
            RCAResult(
                incident_id="INC-011",
                summary="A cause with nothing behind it.",
                root_cause=cause,
                confidence=0.4,
            )


class ContextAndPromptTests(unittest.TestCase):
    def test_context_does_not_load_ground_truth(self):
        with patch("ingestion.incident_loader.load_ground_truth", side_effect=AssertionError("ground truth")):
            context = _context()
        self.assertEqual(context.incident_id, "INC-011")
        ids = set(context.allowed_ids())
        self.assertTrue(any(eid.startswith("ANOMWIN-") for eid in ids))
        self.assertTrue(any(eid.startswith("LOG-") for eid in ids))
        self.assertIn("HIST-007", ids)
        self.assertIn("database_003", ids)
        self.assertIn("payment-api", context.service)

    def test_context_is_deterministic(self):
        self.assertEqual(_context().model_dump(), _context().model_dump())

    def test_prompt_omits_evaluation_fields_and_includes_retrieval(self):
        context = _context()
        prompt = render_prompt(context)
        self.assertNotIn("true_root_cause", prompt)
        self.assertNotRegex(prompt, r"\bscenario\b")
        self.assertIn("HIST-007", prompt)
        self.assertIn("database_003", prompt)
        self.assertIn("Do not assume the first anomaly", prompt)
        self.assertIn("not the cause of this incident", prompt)
        truth = load_ground_truth(incident_path("INC-011", DATA))
        self.assertNotIn(truth.true_root_cause, prompt)
        self.assertNotIn(truth.resolution, prompt)
        self.assertNotIn(truth.fault_start_time.isoformat(), prompt)
        for symptom in truth.expected_symptoms:
            if len(symptom) >= 40:
                self.assertNotIn(symptom, prompt)


class GuardrailTests(unittest.TestCase):
    def test_unknown_evidence_id_is_rejected(self):
        context = _context()
        known = next(iter(context.allowed_ids()))
        cause = _hypothesis("connection waits", "NOT-AN-EVIDENCE-ID")
        draft = RCAResult(
            incident_id="INC-011",
            summary="Cites an id that was never supplied.",
            root_cause=cause,
            confidence=0.7,
            supporting_evidence=[EvidenceReference(
                evidence_id="NOT-AN-EVIDENCE-ID",
                source_type=EvidenceSource.LOG,
                short_description="invented",
            )],
            recommended_actions=[RecommendedAction(
                action="Look again.",
                rationale="The citation is bad.",
                evidence_ids=[known],
            )],
        )
        with self.assertRaises(InvalidRCA):
            validate_rca(draft, context)

    def test_known_ids_are_rewritten_from_the_supplied_text(self):
        context = _context()
        evidence_id = next(eid for eid in context.allowed_ids() if eid.startswith("LOG-"))
        cause = _hypothesis("connection waits", evidence_id, 0.66)
        draft = RCAResult(
            incident_id="INC-011",
            summary="Waits showed up in the logs.",
            root_cause=cause,
            confidence=0.66,
            supporting_evidence=[EvidenceReference(
                evidence_id=evidence_id,
                source_type=EvidenceSource.LOG,
                short_description="invented wording that must be replaced",
            )],
            timeline=[TimelineEntry(
                evidence_id=evidence_id,
                timestamp="1999-01-01T00:00:00",
                description="invented timeline text",
            )],
            recommended_actions=[RecommendedAction(
                action="Inspect connection waits on the alerting service.",
                rationale="The log is in the supplied evidence.",
                evidence_ids=[evidence_id],
            )],
            similar_incidents=[SimilarIncident(
                incident_id="HIST-007",
                similarity_note="Both describe connection waits and latency.",
            )],
        )
        checked = validate_rca(draft, context)
        supplied = context.allowed_ids()[evidence_id].short_description
        self.assertEqual(checked.supporting_evidence[0].short_description, supplied)
        self.assertNotEqual(checked.timeline[0].timestamp, "1999-01-01T00:00:00")
        self.assertEqual(checked.similar_incidents[0].incident_id, "HIST-007")

    def test_malformed_model_output_is_rejected(self):
        context = _context()

        class _Client:
            def __init__(self):
                self.models = self

            def generate_content(self, **_kwargs):
                return SimpleNamespace(parsed=None, text="{not json")

        investigator = GeminiInvestigator(Settings(api_key="test", max_attempts=1), client=_Client())
        with self.assertRaises(InvalidRCA):
            investigator.investigate(context)

    def test_empty_evidence_returns_insufficient_without_calling_the_model(self):
        context = InvestigationContext(
            incident_id="INC-014",
            service="inventory-service",
            severity="LOW",
            title="quiet",
            description="No customer impact recorded.",
            alert_start="2026-02-10T09:43:32",
            alert_end="2026-02-10T10:23:16",
            duration_minutes=39.7,
            involved_services=["inventory-service"],
            retrieval_query="",
            evidence=[],
        )

        class _Client:
            def __init__(self):
                self.models = self

            def generate_content(self, **_kwargs):
                raise AssertionError("model should not be called")

        investigator = GeminiInvestigator(Settings(api_key="test"), client=_Client())
        result = investigator.investigate(context)
        self.assertEqual(result.root_cause.cause, INSUFFICIENT_EVIDENCE)
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.supporting_evidence, [])
        self.assertEqual(insufficient_result("INC-014", "none").root_cause.cause, INSUFFICIENT_EVIDENCE)


class SecretRedactionTests(unittest.TestCase):
    def test_public_message_redacts_supplied_key(self):
        key = "AQ." + ("x" * 40)
        text = _public_message(RuntimeError(f"PERMISSION_DENIED credential={key}"), api_key=key)
        self.assertNotIn(key, text)
        self.assertNotRegex(text, r"AQ\.[A-Za-z0-9_\-]+")

    def test_public_message_hides_api_key_mentions(self):
        text = _public_message(RuntimeError("invalid api_key value"))
        self.assertEqual(text, "The Gemini request failed. Check GENAI_MODEL and credentials.")


if __name__ == "__main__":
    unittest.main()
