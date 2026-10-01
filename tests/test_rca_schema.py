"""Day 9 schema tests. These construct Pydantic models only. They do not call Gemini.

    python -m unittest tests.test_rca_schema -v
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from investigation.evidence import validate_rca  # noqa: E402
from investigation.models import (  # noqa: E402
    GROUND_TRUTH_FIELD_NAMES,
    EvidenceReference,
    EvidenceSource,
    RCAResult,
    RecommendedAction,
    RootCauseHypothesis,
    SimilarIncident,
    TimelineEntry,
)


def _cause(confidence: float = 0.72, evidence_id: str = "LOG-000001") -> RootCauseHypothesis:
    return RootCauseHypothesis(
        cause="connection acquisition delays",
        confidence=confidence,
        supporting_evidence_ids=[evidence_id],
        contradicting_evidence_ids=["ANOM-000004"],
        rationale="Wait logs and a flat memory series point different ways.",
    )


def _reference(
    evidence_id: str = "LOG-000001",
    source_type: EvidenceSource = EvidenceSource.LOG,
) -> EvidenceReference:
    return EvidenceReference(
        evidence_id=evidence_id,
        source_type=source_type,
        short_description="connection wait on payment-api",
    )


def _result(**overrides) -> RCAResult:
    payload = dict(
        incident_id="INC-011",
        summary="Requests waited while borrowing database connections.",
        root_cause=_cause(),
        confidence=0.72,
        alternative_causes=[_cause(0.41, "ANOMWIN-000002")],
        supporting_evidence=[_reference(), _reference("ANOMWIN-000002")],
        contradicting_evidence=[_reference("ANOM-000004")],
        timeline=[TimelineEntry(
            evidence_id="LOG-000001",
            timestamp="2026-02-03T06:18:15",
            description="connection wait on payment-api",
        )],
        recommended_actions=[RecommendedAction(
            action="Inspect pool wait counts on the alerting service.",
            rationale="The cited log is a wait, not a memory climb.",
            evidence_ids=["LOG-000001"],
        )],
        similar_incidents=[SimilarIncident(
            incident_id="HIST-007",
            similarity_note="Both records describe connection waits and latency.",
        )],
    )
    payload.update(overrides)
    return RCAResult(**payload)


class RCASchemaTests(unittest.TestCase):
    def test_valid_result_instantiates(self):
        result = _result()
        self.assertEqual(result.incident_id, "INC-011")
        self.assertEqual(result.root_cause.cause, "connection acquisition delays")
        self.assertEqual(result.confidence, 0.72)
        self.assertEqual(len(result.alternative_causes), 1)
        self.assertEqual(result.similar_incidents[0].incident_id, "HIST-007")

    def test_nested_evidence_references_validate(self):
        ref = _reference("ANOMWIN-000017", EvidenceSource.ANOMALY_WINDOW)
        self.assertEqual(ref.evidence_id, "ANOMWIN-000017")
        self.assertEqual(ref.source_type, EvidenceSource.ANOMALY_WINDOW)
        result = _result(supporting_evidence=[ref])
        self.assertEqual(result.supporting_evidence[0].evidence_id, "ANOMWIN-000017")
        with self.assertRaises(ValidationError):
            EvidenceReference(
                evidence_id="LOG-000001",
                source_type="not-a-source",
                short_description="connection wait",
            )
        with self.assertRaises(ValidationError):
            EvidenceReference(source_type=EvidenceSource.LOG, short_description="missing id")

    def test_invalid_confidence_is_rejected(self):
        for bad in (1.5, -0.01, math.nan, math.inf):
            with self.assertRaises(ValidationError):
                _cause(confidence=bad)
        with self.assertRaises(ValidationError):
            _result(confidence=0.2)

    def test_required_fields_are_enforced(self):
        for field in ("incident_id", "summary", "root_cause", "confidence"):
            payload = _result().model_dump()
            payload.pop(field)
            with self.assertRaises(ValidationError):
                RCAResult.model_validate(payload)
        with self.assertRaises(ValidationError):
            RootCauseHypothesis(confidence=0.5, supporting_evidence_ids=["LOG-000001"], rationale="no cause")
        with self.assertRaises(ValidationError):
            _result(summary="")

    def test_alternative_hypotheses_validate(self):
        result = _result()
        self.assertIsInstance(result.alternative_causes[0], RootCauseHypothesis)
        self.assertEqual(result.alternative_causes[0].supporting_evidence_ids, ["ANOMWIN-000002"])
        with self.assertRaises(ValidationError):
            _result(alternative_causes=[{"cause": "dependency wait", "confidence": 2, "rationale": "no"}])

    def test_recommended_actions_validate(self):
        result = _result()
        self.assertEqual(result.recommended_actions[0].evidence_ids, ["LOG-000001"])
        with self.assertRaises(ValidationError):
            RecommendedAction(rationale="missing the action", evidence_ids=["LOG-000001"])
        with self.assertRaises(ValidationError):
            RecommendedAction(action="Inspect waits.", rationale="", evidence_ids=["LOG-000001"])

    def test_evidence_ids_are_citation_keys(self):
        result = _result()
        self.assertEqual(result.root_cause.supporting_evidence_ids, ["LOG-000001"])
        self.assertEqual(result.root_cause.contradicting_evidence_ids, ["ANOM-000004"])
        self.assertEqual(result.timeline[0].evidence_id, "LOG-000001")
        padded = _reference("  HIST-007  ")
        self.assertEqual(padded.evidence_id, "HIST-007")
        for blank in ("", "   "):
            with self.assertRaises(ValidationError):
                _reference(blank)
            with self.assertRaises(ValidationError):
                _cause(evidence_id=blank)

    def test_no_ground_truth_fields_on_the_result(self):
        fields = set(RCAResult.model_fields)
        self.assertFalse(fields & GROUND_TRUTH_FIELD_NAMES)
        for name in ("true_root_cause", "scenario", "fault_start_time", "expected_symptoms"):
            payload = _result().model_dump()
            payload[name] = "should-not-fit"
            with self.assertRaises(ValidationError):
                RCAResult.model_validate(payload)

    def test_malformed_timeline_is_rejected(self):
        with self.assertRaises(ValidationError):
            TimelineEntry(evidence_id="", description="connection wait")
        with self.assertRaises(ValidationError):
            TimelineEntry(evidence_id="LOG-000001", description="")
        with self.assertRaises(ValidationError):
            _result(timeline=[{"evidence_id": "LOG-000001"}])

    def test_id_membership_check_is_not_part_of_the_schema(self):
        """The schema accepts a well-formed id. evidence.validate_rca decides if it was supplied."""
        self.assertFalse(hasattr(RCAResult, "validate_rca"))
        self.assertEqual(validate_rca.__module__, "investigation.evidence")
        invented = _result(
            root_cause=_cause(evidence_id="NOT-SUPPLIED"),
            supporting_evidence=[_reference("NOT-SUPPLIED")],
            contradicting_evidence=[],
            alternative_causes=[],
            timeline=[],
            recommended_actions=[RecommendedAction(
                action="Do not treat this id as observed.",
                rationale="The schema only checks the shape.",
                evidence_ids=["NOT-SUPPLIED"],
            )],
            similar_incidents=[],
        )
        self.assertEqual(invented.root_cause.supporting_evidence_ids, ["NOT-SUPPLIED"])


if __name__ == "__main__":
    unittest.main()
