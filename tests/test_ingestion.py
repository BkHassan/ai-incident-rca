"""Tests for the ingestion layer, run against the generated dataset in data/.

    python -m unittest discover -s tests -v

Invalid inputs are built by corrupting single fields of real records from the dataset.
"""

from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion import (  # noqa: E402
    CONTEXT_FIELDS,
    DEFAULT_DATA_DIR,
    GROUND_TRUTH_FIELDS,
    EventType,
    IncidentContext,
    IncidentEvaluationRecord,
    IncidentEvidenceBundle,
    IncidentGroundTruth,
    IngestionError,
    LogLevel,
    classify_event,
    incident_path,
    list_incident_ids,
    load_evaluation_record,
    load_evidence_bundle,
    load_ground_truth,
    load_incident_context,
    load_logs,
    load_metrics,
)

RAW = DEFAULT_DATA_DIR / "raw"
INCIDENT = "INC-011"      # DB pool exhaustion on payment-api
NORMAL_INCIDENT = "INC-014"
LOG_FILE = RAW / "logs" / f"{INCIDENT}.jsonl"
METRIC_FILE = RAW / "metrics" / f"{INCIDENT}.csv"
GROUND_TRUTH_ONLY = set(GROUND_TRUTH_FIELDS) - {"incident_id"}


def raw_log_lines() -> list[str]:
    return LOG_FILE.read_text(encoding="utf-8").splitlines()


def raw_metric_rows() -> tuple[list[str], list[list[str]]]:
    with METRIC_FILE.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def index_counts() -> dict[str, tuple[int, int]]:
    with (DEFAULT_DATA_DIR / "generated" / "incidents_index.csv").open(encoding="utf-8", newline="") as fh:
        return {r["incident_id"]: (int(r["log_records"]), int(r["metric_rows"])) for r in csv.DictReader(fh)}


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.tmp / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_csv(self, name: str, header: list[str], rows: list[list[str]]) -> Path:
        path = self.tmp / name
        with path.open("w", encoding="utf-8", newline="") as fh:
            csv.writer(fh, lineterminator="\n").writerows([header, *rows])
        return path


class LogParsingTests(TempDirTestCase):
    def test_valid_log_file_parses_every_record(self):
        logs = load_logs(LOG_FILE, incident_id=INCIDENT)
        self.assertEqual(len(logs), index_counts()[INCIDENT][0])
        first_raw = json.loads(raw_log_lines()[0])
        first = logs[0]
        self.assertEqual(first.message, first_raw["message"])
        self.assertEqual((first.service, first.host, first.logger), (first_raw["service"], first_raw["host"], first_raw["logger"]))
        self.assertIs(first.level, LogLevel(first_raw["level"]))
        self.assertEqual(first.trace_id, first_raw["trace_id"])
        self.assertEqual(first.incident_id, INCIDENT)

    def test_messages_are_preserved_exactly(self):
        raw_messages = sorted(json.loads(line)["message"] for line in raw_log_lines())
        self.assertEqual(sorted(event.message for event in load_logs(LOG_FILE)), raw_messages)

    def test_levels_are_normalized(self):
        record = json.loads(raw_log_lines()[0])
        lines = [json.dumps({**record, "level": level}) for level in ("info", " Warn ", "WARNING", "error")]
        levels = [event.level for event in load_logs(self.write("levels.jsonl", "\n".join(lines) + "\n"))]
        self.assertEqual(levels, [LogLevel.INFO, LogLevel.WARN, LogLevel.WARN, LogLevel.ERROR])

    def test_invalid_log_records_are_rejected_with_location(self):
        good = raw_log_lines()[0]
        record = json.loads(good)
        missing_trace = {k: v for k, v in record.items() if k != "trace_id"}
        lines = [good,
                 json.dumps({**record, "level": "VERBOSE"}),
                 json.dumps({**record, "timestamp": "03/02/2026 04:56"}),
                 "{not json",
                 json.dumps(missing_trace),
                 json.dumps({**record, "incident_id": "INC-999"})]
        path = self.write("broken.jsonl", "\n".join(lines) + "\n")
        with self.assertRaises(IngestionError) as caught:
            load_logs(path, incident_id=INCIDENT)
        err = caught.exception
        self.assertEqual(err.path, path)
        self.assertEqual([issue.location for issue in err.issues], ["line 2", "line 3", "line 4", "line 5", "line 6"])
        reasons = [issue.reason for issue in err.issues]
        self.assertIn("unknown log level 'VERBOSE'", reasons[0])
        self.assertIn("invalid ISO-8601 timestamp", reasons[1])
        self.assertIn("invalid JSON", reasons[2])
        self.assertIn("trace_id", reasons[3])
        self.assertIn("expected INC-011", reasons[4])
        self.assertEqual(err.issues[0].incident_id, INCIDENT)
        self.assertIn(str(path), str(err))

    def test_empty_log_file_is_rejected(self):
        with self.assertRaises(IngestionError):
            load_logs(self.write("empty.jsonl", ""))

    def test_log_timestamps_are_naive_datetimes(self):
        first = load_logs(LOG_FILE)[0]
        self.assertEqual(first.timestamp, datetime(2026, 2, 3, 4, 56, 3, 446000))
        self.assertIsNone(first.timestamp.tzinfo)

    def test_timezone_aware_timestamp_is_rejected(self):
        record = json.loads(raw_log_lines()[0])
        path = self.write("tz.jsonl", json.dumps({**record, "timestamp": "2026-02-03T04:56:03.446+00:00"}) + "\n")
        with self.assertRaises(IngestionError) as caught:
            load_logs(path)
        self.assertIn("UTC offset", str(caught.exception))

    def test_logs_are_returned_in_timestamp_order(self):
        lines = raw_log_lines()
        shuffled = self.write("reversed.jsonl", "\n".join(reversed(lines)) + "\n")
        events = load_logs(shuffled)
        stamps = [event.timestamp for event in events]
        self.assertEqual(stamps, sorted(stamps))
        self.assertEqual(stamps, [event.timestamp for event in load_logs(LOG_FILE)])


class EventTypeTests(unittest.TestCase):
    def test_messages_from_the_dataset_map_to_event_types(self):
        cases = {
            ('"POST /api/v1/payments HTTP/1.1" 200 upstream=payment-api duration=149ms', "INFO"): EventType.REQUEST_COMPLETED,
            ('"GET /api/v1/cart HTTP/1.1" 503 upstream=orders-api duration=3012ms', "ERROR"): EventType.REQUEST_FAILED,
            ("request started method=GET path=/api/v1/cart", "INFO"): EventType.REQUEST_STARTED,
            ("GET /healthz 200", "INFO"): EventType.HEALTH_CHECK_PASSED,
            ("GET /healthz 503 (db: timeout)", "WARN"): EventType.HEALTH_CHECK_FAILED,
            ("HikariPool-1 - Connection is not available, request timed out after 30000ms.", "ERROR"): EventType.DB_TIMEOUT,
            ("Database connection timeout", "ERROR"): EventType.DB_TIMEOUT,
            ("httpx.ReadTimeout: timed out calling payment-api POST /api/v1/payments after 5s", "ERROR"): EventType.DOWNSTREAM_TIMEOUT,
            ("Retry 'acquirer-gateway' attempt 2 of 3 after SocketTimeoutException", "WARN"): EventType.RETRY,
            ("cache hit key=cart:1234", "INFO"): EventType.CACHE_HIT,
            ("GC pause (G1 Evacuation Pause) (young) 12ms", "INFO"): EventType.GC_PAUSE,
            ("duration: 812 ms  statement: SELECT * FROM order_items WHERE order_id = ANY($1)", "WARN"): EventType.SLOW_DB_QUERY,
            ("duration: 3 ms  statement: SELECT * FROM order_items WHERE order_id = ANY($1)", "INFO"): EventType.DB_QUERY,
            ("reserve stock sku=SKU-1: context deadline exceeded", "ERROR"): EventType.OPERATION_TIMEOUT,
        }
        for (message, level), expected in cases.items():
            with self.subTest(message=message):
                self.assertIs(classify_event(message, level), expected)

    def test_event_types_never_name_a_scenario(self):
        labels = ("DB_CONNECTION_POOL_EXHAUSTION", "MEMORY_LEAK", "DOWNSTREAM_SERVICE_TIMEOUT", "NORMAL",
                  "POOL_EXHAUSTION", "LEAK", "ROOT_CAUSE")
        for event_type in EventType:
            for label in labels:
                self.assertNotIn(label, event_type.value.upper(), event_type)

    def test_every_record_of_an_incident_gets_a_known_event_type(self):
        unknown = [e.message for e in load_logs(LOG_FILE) if e.event_type is EventType.UNKNOWN]
        self.assertEqual(unknown, [])


class MetricLoadingTests(TempDirTestCase):
    def test_valid_metric_file_parses_every_row(self):
        points = load_metrics(METRIC_FILE, incident_id=INCIDENT)
        self.assertEqual(len(points), index_counts()[INCIDENT][1])
        header, rows = raw_metric_rows()
        raw = dict(zip(header, rows[0]))
        point = next(p for p in points if p.service == raw["service"] and p.timestamp == datetime.fromisoformat(raw["timestamp"]))
        for column in ("cpu_usage", "memory_usage", "request_rate", "latency_ms", "error_rate"):
            self.assertEqual(getattr(point, column), float(raw[column]), column)
            self.assertIsInstance(getattr(point, column), float)

    def test_blank_metric_values_become_none(self):
        points = load_metrics(METRIC_FILE)
        for point in points:
            self.assertEqual(point.db_connection_utilization is None, point.service == "api-gateway", point)
            no_downstream = point.service in ("database", "recommendation-service")
            self.assertEqual(point.downstream_latency_ms is None, no_downstream, point)

    def test_invalid_metric_values_are_detected(self):
        header, rows = raw_metric_rows()
        col = {name: i for i, name in enumerate(header)}
        base = next(r for r in rows if r[col["service"]] == "payment-api")

        def variant(**changes):
            row = list(base)
            for name, value in changes.items():
                row[col[name]] = value
            return row

        broken = [base,
                  variant(cpu_usage="abc"),
                  variant(cpu_usage=""),
                  variant(error_rate="150"),
                  variant(timestamp="yesterday"),
                  variant(latency_ms="nan")]
        path = self.write_csv("broken.csv", header, broken)
        with self.assertRaises(IngestionError) as caught:
            load_metrics(path)
        err = caught.exception
        self.assertEqual([issue.location for issue in err.issues], ["row 3", "row 4", "row 5", "row 6", "row 7"])
        reasons = [issue.reason for issue in err.issues]
        self.assertIn("'abc' is not a number", reasons[0])
        self.assertIn("blank but required", reasons[1])
        self.assertIn("error_rate", reasons[2])
        self.assertIn("invalid ISO-8601 timestamp", reasons[3])
        self.assertIn("latency_ms", reasons[4])
        self.assertEqual(err.issues[0].incident_id, INCIDENT)

    def test_missing_column_is_reported(self):
        header, rows = raw_metric_rows()
        keep = [i for i, name in enumerate(header) if name != "error_rate"]
        path = self.write_csv("no_error_rate.csv", [header[i] for i in keep], [[r[i] for i in keep] for r in rows[:3]])
        with self.assertRaises(IngestionError) as caught:
            load_metrics(path)
        self.assertIn("missing columns ['error_rate']", str(caught.exception))

    def test_duplicate_rows_are_reported(self):
        header, rows = raw_metric_rows()
        path = self.write_csv("dup.csv", header, [rows[0], rows[1], rows[0]])
        with self.assertRaises(IngestionError) as caught:
            load_metrics(path)
        self.assertIn("duplicate row", str(caught.exception))

    def test_metric_timestamps_are_parsed(self):
        header, rows = raw_metric_rows()
        first = load_metrics(METRIC_FILE)[0]
        self.assertEqual(first.timestamp, datetime.fromisoformat(rows[0][header.index("timestamp")]))
        self.assertIsNone(first.timestamp.tzinfo)

    def test_metrics_are_returned_in_timestamp_order(self):
        header, rows = raw_metric_rows()
        points = load_metrics(self.write_csv("reversed.csv", header, list(reversed(rows))))
        keys = [(p.timestamp, p.service) for p in points]
        self.assertEqual(keys, sorted(keys))
        self.assertEqual(points, load_metrics(METRIC_FILE))


class IncidentLoadingTests(TempDirTestCase):
    def test_incident_context_loads(self):
        raw = json.loads(incident_path(INCIDENT).read_text(encoding="utf-8"))
        context = load_incident_context(incident_path(INCIDENT))
        self.assertEqual(context.incident_id, INCIDENT)
        self.assertEqual(context.service, raw["service"])
        self.assertEqual(context.severity.value, raw["severity"])
        self.assertEqual(context.description, raw["description"])
        self.assertEqual(context.start_time, datetime.fromisoformat(raw["start_time"]))
        self.assertLess(context.start_time, context.end_time)

    def test_ground_truth_is_separate_from_context(self):
        self.assertEqual(set(CONTEXT_FIELDS) & set(GROUND_TRUTH_FIELDS), {"incident_id"})
        self.assertFalse(GROUND_TRUTH_ONLY & set(IncidentContext.model_fields))
        context = load_incident_context(incident_path(INCIDENT))
        for field in GROUND_TRUTH_ONLY:
            self.assertFalse(hasattr(context, field), field)
        # The context model refuses ground-truth fields outright.
        with self.assertRaises(ValueError):
            IncidentContext.model_validate({**context.model_dump(), "true_root_cause": "DB_CONNECTION_POOL_EXHAUSTION"})

    def test_ground_truth_loads(self):
        raw = json.loads(incident_path(INCIDENT).read_text(encoding="utf-8"))
        truth = load_ground_truth(incident_path(INCIDENT))
        self.assertIsInstance(truth, IncidentGroundTruth)
        self.assertEqual((truth.scenario, truth.true_root_cause, truth.root_cause_service, truth.root_cause_variant),
                         (raw["scenario"], raw["true_root_cause"], raw["root_cause_service"], raw["root_cause_variant"]))
        normal = load_ground_truth(incident_path(NORMAL_INCIDENT))
        self.assertEqual(normal.scenario, "NORMAL")
        self.assertIsNone(normal.true_root_cause)
        self.assertIsNone(normal.fault_start_time)

    def test_unclassified_metadata_field_is_rejected(self):
        raw = json.loads(incident_path(INCIDENT).read_text(encoding="utf-8"))
        path = self.write(f"{INCIDENT}.json", json.dumps({**raw, "suspected_cause": "x"}))
        with self.assertRaises(IngestionError) as caught:
            load_incident_context(path)
        self.assertIn("suspected_cause", str(caught.exception))

    def test_invalid_severity_is_reported_with_incident(self):
        raw = json.loads(incident_path(INCIDENT).read_text(encoding="utf-8"))
        path = self.write(f"{INCIDENT}.json", json.dumps({**raw, "severity": "SEV1"}))
        with self.assertRaises(IngestionError) as caught:
            load_incident_context(path)
        self.assertIn("severity", str(caught.exception))
        self.assertEqual(caught.exception.incident_id, INCIDENT)


class EvidenceBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_evidence_bundle(INCIDENT)
        cls.raw = json.loads(incident_path(INCIDENT).read_text(encoding="utf-8"))

    def test_bundle_has_only_operational_fields(self):
        self.assertEqual(set(IncidentEvidenceBundle.model_fields), {"context", "logs", "metrics"})
        self.assertFalse(hasattr(self.bundle, "ground_truth"))

    def test_bundle_does_not_contain_true_root_cause(self):
        dumped = self.bundle.model_dump(mode="json")
        keys = set(dumped) | set(dumped["context"])
        keys |= {k for record in dumped["logs"] + dumped["metrics"] for k in record}
        self.assertFalse(GROUND_TRUTH_ONLY & keys)
        text = json.dumps(dumped)
        for field in ("true_root_cause", "scenario", "root_cause_variant", "root_cause_detail", "resolution"):
            self.assertNotIn(str(self.raw[field]), text, field)

    def test_bundle_contents_are_consistent_and_ordered(self):
        counts = index_counts()[INCIDENT]
        self.assertEqual((len(self.bundle.logs), len(self.bundle.metrics)), counts)
        self.assertTrue(all(r.incident_id == INCIDENT for r in (*self.bundle.logs, *self.bundle.metrics)))
        stamps = [e.timestamp for e in self.bundle.logs]
        self.assertEqual(stamps, sorted(stamps))

    def test_bundle_rejects_records_from_another_incident(self):
        other = load_evidence_bundle(NORMAL_INCIDENT)
        with self.assertRaises(ValueError):
            IncidentEvidenceBundle(context=self.bundle.context, logs=self.bundle.logs, metrics=other.metrics)

    def test_evaluation_record_pairs_evidence_with_ground_truth(self):
        record = load_evaluation_record(INCIDENT)
        self.assertIsInstance(record, IncidentEvaluationRecord)
        self.assertEqual(record.evidence, self.bundle)
        self.assertEqual(record.ground_truth.true_root_cause, self.raw["true_root_cause"])
        with self.assertRaises(ValueError):
            IncidentEvaluationRecord(evidence=self.bundle, ground_truth=load_ground_truth(incident_path(NORMAL_INCIDENT)))


class FullDatasetTests(unittest.TestCase):
    def test_every_incident_loads_into_a_bundle(self):
        counts = index_counts()
        ids = list_incident_ids()
        self.assertEqual(ids, sorted(counts))
        self.assertGreaterEqual(len(ids), 35)
        for incident_id in ids:
            with self.subTest(incident_id=incident_id):
                bundle = load_evidence_bundle(incident_id)
                self.assertEqual((len(bundle.logs), len(bundle.metrics)), counts[incident_id])


if __name__ == "__main__":
    unittest.main()
