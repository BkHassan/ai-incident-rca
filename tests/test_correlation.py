"""Tests for observational temporal correlation.

    python -m unittest tests.test_correlation -v
"""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from correlation import (  # noqa: E402
    CorrelationConfig,
    EvidenceItem,
    IncidentTimeline,
    SourceType,
    TimelineEvent,
    correlate_incident,
)
from correlation.evidence import is_relevant_log  # noqa: E402
from correlation.models import EvidenceType  # noqa: E402
from detection.models import (  # noqa: E402
    AnomalyPoint,
    AnomalySeverity,
    AnomalyWindow,
    DetectionMethod,
    Direction,
    IncidentAnomalyReport,
)
from detection import DEFAULT_CONFIG as DETECTOR_CONFIG  # noqa: E402
from ingestion import GROUND_TRUTH_FIELDS, load_evidence_bundle  # noqa: E402
from ingestion.models import (  # noqa: E402
    EventType,
    IncidentContext,
    IncidentEvidenceBundle,
    LogEvent,
    LogLevel,
    MetricPoint,
)

T0 = datetime(2026, 2, 1, 10, 0, 0)
INCIDENT = "INC-900"
STEADY = {"cpu_usage": 30.0, "memory_usage": 45.0, "request_rate": 100.0, "latency_ms": 100.0, "error_rate": 0.3,
          "db_connection_utilization": 20.0, "downstream_latency_ms": 50.0}
LEAKAGE_FIELDS = set(GROUND_TRUTH_FIELDS) - {"incident_id", "affected_services"}
CAUSAL_PHRASES = (" caused ", " causing ", " because ", " due to ", " led to ", " root cause",
                  " responsible for ", " triggered ")


def ts(minutes: float) -> datetime:
    return T0 + timedelta(minutes=minutes)


def log_event(minutes: float, message: str, *, service: str = "payment-api", level: str = "ERROR",
              event_type: EventType = EventType.DB_TIMEOUT, incident_id: str = INCIDENT) -> LogEvent:
    return LogEvent(timestamp=ts(minutes), incident_id=incident_id, service=service, host=f"{service}-0",
                    level=level, logger="test", message=message, trace_id=None, event_type=event_type)


def context(start: float = 40, end: float = 70, service: str = "payment-api") -> IncidentContext:
    return IncidentContext(
        incident_id=INCIDENT, title="test alert", service=service, severity="HIGH",
        start_time=ts(start), end_time=ts(end), duration_minutes=end - start,
        window_start=ts(0), window_end=ts(120), description="Elevated latency on payment-api.",
    )


def bundle(logs: list[LogEvent], ctx: IncidentContext | None = None) -> IncidentEvidenceBundle:
    ctx = ctx or context()
    metric = MetricPoint(timestamp=ts(0), incident_id=INCIDENT, service=ctx.service, **STEADY)
    return IncidentEvidenceBundle(context=ctx, logs=tuple(sorted(logs, key=lambda e: e.timestamp)), metrics=(metric,))


def point(minutes: float, metric: str = "latency_ms", service: str = "payment-api",
          value: float = 2000.0, z: float = 40.0) -> AnomalyPoint:
    return AnomalyPoint(
        incident_id=INCIDENT, timestamp=ts(minutes), service=service, metric_name=metric, value=value,
        baseline_mean=100.0, baseline_std=5.0, baseline_points=15, z_score=z, deviation=value - 100.0,
        direction=Direction.UP, severity=AnomalySeverity.HIGH if abs(z) >= 50 else AnomalySeverity.MEDIUM,
        detection_method=DetectionMethod.ROLLING_ZSCORE, absolute_threshold_exceeded=False,
    )


def window(start: float, end: float, metric: str = "latency_ms", service: str = "payment-api",
           count: int = 5) -> AnomalyWindow:
    return AnomalyWindow(
        incident_id=INCIDENT, start_time=ts(start), end_time=ts(end), duration_minutes=end - start,
        severity=AnomalySeverity.HIGH, anomaly_count=count, affected_services=(service,),
        affected_metrics=(metric,), affected_series=(f"{service}:{metric}",),
        peak_deviation=80.0, peak_z_score=80.0, peak_metric=metric, peak_service=service,
        peak_timestamp=ts(start), detection_methods=(DetectionMethod.ROLLING_ZSCORE,),
    )


def report(points: list[AnomalyPoint], windows: list[AnomalyWindow]) -> IncidentAnomalyReport:
    return IncidentAnomalyReport(
        incident_id=INCIDENT, config=DETECTOR_CONFIG, series_analyzed=1, observations_analyzed=len(points),
        points=tuple(points), windows=tuple(windows),
    )


class RelevanceTests(unittest.TestCase):
    def test_relevance_does_not_depend_on_scenario(self):
        timeout = log_event(40, "Database connection timeout")
        completed = log_event(40, "request completed", level="INFO", event_type=EventType.REQUEST_COMPLETED)
        deploy = log_event(10, "rolling update complete: payment-api v1.2", level="INFO",
                           event_type=EventType.DEPLOYMENT_COMPLETED)
        self.assertTrue(is_relevant_log(timeout))
        self.assertTrue(is_relevant_log(deploy))
        self.assertFalse(is_relevant_log(completed))


class TimelineOrderTests(unittest.TestCase):
    def test_events_are_sorted_chronologically(self):
        logs = [
            log_event(50, "later timeout"),
            log_event(20, "rolling update complete", level="INFO", event_type=EventType.DEPLOYMENT_COMPLETED),
            log_event(45, "db timeout"),
        ]
        timeline = correlate_incident(bundle(logs), report([point(46)], [window(45, 55)]))
        stamps = [e.timestamp for e in timeline.events]
        self.assertEqual(stamps, sorted(stamps))

    def test_first_observed_event_is_the_earliest(self):
        logs = [
            log_event(45, "db timeout"),
            log_event(15, "rolling update started", level="INFO", event_type=EventType.DEPLOYMENT_STARTED),
        ]
        timeline = correlate_incident(bundle(logs), report([point(46)], [window(45, 55)]))
        self.assertIsNotNone(timeline.first_observed_event)
        self.assertEqual(timeline.first_observed_event.timestamp, ts(15))
        self.assertIn("deployment started", timeline.first_observed_event.title)
        self.assertEqual(timeline.first_observed_event.timestamp, min(e.timestamp for e in timeline.events))

    def test_equal_timestamps_are_ordered_deterministically(self):
        logs = [
            log_event(45, "timeout B", service="orders-api"),
            log_event(45, "timeout A", service="payment-api"),
        ]
        timeline = correlate_incident(bundle(logs), report([], []))
        at_45 = [e for e in timeline.events if e.timestamp == ts(45) and e.source_type is SourceType.LOG]
        self.assertEqual([e.service for e in at_45], ["orders-api", "payment-api"])
        again = correlate_incident(bundle(logs), report([], []))
        self.assertEqual([e.evidence_id for e in timeline.events], [e.evidence_id for e in again.events])


class WindowAndLinkTests(unittest.TestCase):
    def test_anomaly_windows_are_represented(self):
        win = window(45, 55, metric="latency_ms")
        timeline = correlate_incident(bundle([]), report([point(45), point(50)], [win]))
        self.assertEqual(len(timeline.anomaly_windows), 1)
        self.assertEqual(timeline.anomaly_windows[0].start_time, ts(45))
        self.assertEqual(timeline.anomaly_windows[0].peak_metric, "latency_ms")
        window_events = [e for e in timeline.events if e.source_type is SourceType.ANOMALY_WINDOW]
        self.assertEqual(len(window_events), 1)
        self.assertTrue(window_events[0].evidence_id.startswith("ANOMWIN-"))

    def test_relevant_logs_are_linked_to_nearby_windows(self):
        logs = [log_event(47, "Database connection timeout")]
        win = window(45, 50)
        timeline = correlate_incident(bundle(logs), report([point(45)], [win]))
        window_item = next(i for i in timeline.evidence_items if i.evidence_type is EvidenceType.ANOMALY_WINDOW)
        log_item = next(i for i in timeline.evidence_items if i.source_type is SourceType.LOG)
        self.assertIn(log_item.evidence_id, window_item.related_evidence_ids)

    def test_distant_logs_are_excluded(self):
        logs = [
            log_event(2, "old timeout far from the alert"),
            log_event(45, "timeout during the alert"),
        ]
        win = window(44, 50)
        timeline = correlate_incident(bundle(logs), report([point(45)], [win]))
        messages = " ".join(e.description for e in timeline.events)
        self.assertIn("timeout during the alert", messages)
        self.assertNotIn("old timeout far from the alert", messages)

    def test_multiple_services_appear(self):
        logs = [
            log_event(45, "payment timeout", service="payment-api"),
            log_event(46, "gateway 503", service="api-gateway", event_type=EventType.REQUEST_FAILED),
        ]
        points = [point(45, service="payment-api"), point(46, metric="error_rate", service="api-gateway")]
        windows = [window(45, 50, service="payment-api"), window(46, 50, metric="error_rate", service="api-gateway")]
        timeline = correlate_incident(bundle(logs), report(points, windows))
        self.assertGreaterEqual(set(timeline.involved_services), {"payment-api", "api-gateway"})


class EvidenceIdTests(unittest.TestCase):
    def test_evidence_ids_are_unique_and_prefixed(self):
        logs = [log_event(45, "timeout"), log_event(20, "rolling update complete", level="INFO",
                                                    event_type=EventType.DEPLOYMENT_COMPLETED)]
        timeline = correlate_incident(bundle(logs), report([point(46)], [window(45, 55)]))
        ids = [item.evidence_id for item in timeline.evidence_items]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(any(i.startswith("LOG-") for i in ids))
        self.assertTrue(any(i.startswith("ANOM-") for i in ids))
        self.assertTrue(any(i.startswith("ANOMWIN-") for i in ids))
        event_ids = [e.evidence_id for e in timeline.events]
        self.assertEqual(set(event_ids), set(ids))


class NoGroundTruthTests(unittest.TestCase):
    def test_models_have_no_root_cause_fields(self):
        forbidden = LEAKAGE_FIELDS | {"root_cause"}
        for model in (IncidentTimeline, TimelineEvent, EvidenceItem, CorrelationConfig):
            with self.subTest(model=model.__name__):
                self.assertFalse(forbidden & set(model.model_fields))

    def test_correlation_code_never_touches_ground_truth(self):
        forbidden = ("load_ground_truth", "load_evaluation_record", "IncidentGroundTruth",
                     "IncidentEvaluationRecord", "true_root_cause", "root_cause_service",
                     "root_cause_variant", "root_cause_detail", "fault_start_time", "expected_symptoms")
        for path in sorted((ROOT / "src" / "correlation").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for name in forbidden:
                with self.subTest(file=path.name, name=name):
                    self.assertNotIn(name, source)

    def test_output_contains_no_ground_truth_and_no_causal_language(self):
        logs = [
            log_event(20, "rolling update complete: payment-api v3.5.0", level="INFO",
                      event_type=EventType.DEPLOYMENT_COMPLETED),
            log_event(45, "Database connection timeout"),
        ]
        timeline = correlate_incident(bundle(logs), report([point(46)], [window(45, 55)]))
        dumped = timeline.model_dump(mode="json")
        keys = set(dumped) | {k for e in dumped["events"] for k in e} | {k for i in dumped["evidence_items"] for k in i}
        self.assertFalse(LEAKAGE_FIELDS & keys)
        text = " ".join(e.title.lower() for e in timeline.events)
        for phrase in CAUSAL_PHRASES:
            self.assertNotIn(phrase.strip(), text)
        for label in ("DB_CONNECTION_POOL_EXHAUSTION", "MEMORY_LEAK", "DOWNSTREAM_SERVICE_TIMEOUT", "true_root_cause"):
            self.assertNotIn(label, text)

    def test_correlate_accepts_an_evidence_bundle_without_labels(self):
        real = load_evidence_bundle("INC-011")
        from detection.models import IncidentAnomalyReport
        path = ROOT / "data" / "derived" / "anomalies" / "INC-011.json"
        timeline = correlate_incident(real, IncidentAnomalyReport.model_validate_json(path.read_text(encoding="utf-8")))
        self.assertEqual(timeline.incident_id, "INC-011")
        self.assertTrue(timeline.events)
        self.assertIsNotNone(timeline.first_observed_event)


class NormalCaseTests(unittest.TestCase):
    def test_normal_incident_still_gets_a_small_timeline(self):
        real = load_evidence_bundle("INC-014")
        from detection.models import IncidentAnomalyReport
        path = ROOT / "data" / "derived" / "anomalies" / "INC-014.json"
        anomalies = IncidentAnomalyReport.model_validate_json(path.read_text(encoding="utf-8"))
        timeline = correlate_incident(real, anomalies)
        self.assertEqual(timeline.incident_id, "INC-014")
        self.assertGreater(len(timeline.events), 0)
        self.assertLess(len(timeline.events), 80)


if __name__ == "__main__":
    unittest.main()
