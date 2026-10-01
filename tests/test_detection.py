"""Tests for the statistical anomaly detector.

    python -m unittest discover -s tests -v

Unit tests use small deterministic series built with the real ``MetricPoint`` model.
Integration tests run the detector on incidents from the generated dataset.
"""

from __future__ import annotations

import math
import statistics
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from detection import (  # noqa: E402
    AnomalyPoint,
    AnomalySeverity,
    AnomalyWindow,
    DetectionMethod,
    DetectorConfig,
    Direction,
    IncidentAnomalyReport,
    MetricRule,
    SeverityThresholds,
    build_anomaly_windows,
    causal_rolling_baseline,
    detect_anomalies,
    detect_incident,
    severity_for_z,
    zscore,
)
from detection.baseline import BaselineStats  # noqa: E402
from ingestion import GROUND_TRUTH_FIELDS, MetricPoint, load_evidence_bundle  # noqa: E402

T0 = datetime(2026, 1, 1, 0, 0)
INCIDENT = "INC-900"
STEADY = {"cpu_usage": 30.0, "memory_usage": 45.0, "request_rate": 100.0, "latency_ms": 100.0, "error_rate": 0.3,
          "db_connection_utilization": None, "downstream_latency_ms": None}
# Names that would leak the answer into detection. ``affected_services`` is omitted: on
# AnomalyWindow it means "services that produced anomaly points", not the ground-truth list.
LEAKAGE_FIELDS = set(GROUND_TRUTH_FIELDS) - {"incident_id", "affected_services"}


def wobble(i: int, amplitude: float) -> float:
    """Deterministic noise in [-amplitude, amplitude]."""
    return amplitude * math.sin(1.7 * i) * math.cos(0.3 * i)


def series(values: list[float | None], metric: str = "memory_usage", service: str = "orders-api",
           start: int = 0, incident_id: str = INCIDENT) -> list[MetricPoint]:
    """One service's metrics, one per minute; ``metric`` follows ``values`` and the rest stay steady."""
    return [MetricPoint(timestamp=T0 + timedelta(minutes=start + i), incident_id=incident_id, service=service,
                        **{**STEADY, metric: value}) for i, value in enumerate(values)]


def of_metric(points: list[AnomalyPoint], metric: str) -> list[AnomalyPoint]:
    return [p for p in points if p.metric_name == metric]


class BaselineTests(unittest.TestCase):
    def test_baseline_excludes_the_current_observation(self):
        values = [float(v) for v in (5, 7, 6, 9, 4, 8, 100, 6, 5, 7, 3, 9)]
        stats = causal_rolling_baseline(values, window=4, min_points=3)
        for i, got in enumerate(stats):
            previous = values[max(0, i - 4):i]
            if len(previous) < 3:
                self.assertIsNone(got, i)
                continue
            self.assertAlmostEqual(got.mean, statistics.fmean(previous))
            self.assertAlmostEqual(got.std, statistics.stdev(previous))
            self.assertEqual(got.count, len(previous))
        # The outlier at index 6 does not raise its own baseline, only the ones after it.
        self.assertLess(stats[6].mean, 10)
        self.assertGreater(stats[7].mean, 10)

    def test_baseline_matches_pandas_shifted_rolling_window(self):
        values = [50 + wobble(i, 3) for i in range(60)]
        expected = pd.Series(values).shift(1).rolling(15, min_periods=10)
        means, stds = expected.mean().tolist(), expected.std().tolist()
        for i, got in enumerate(causal_rolling_baseline(values, window=15, min_points=10)):
            if got is None:
                self.assertTrue(math.isnan(means[i]))
            else:
                self.assertAlmostEqual(got.mean, means[i], places=9)
                self.assertAlmostEqual(got.std, stds[i], places=9)

    def test_baseline_never_uses_future_values(self):
        values = [50 + wobble(i, 1) for i in range(40)]
        changed = values[:25] + [500.0] * 15
        self.assertEqual(causal_rolling_baseline(values, 15, 10)[:26], causal_rolling_baseline(changed, 15, 10)[:26])

    def test_detection_before_a_point_ignores_values_after_it(self):
        values = [45 + wobble(i, 0.3) for i in range(90)]
        changed = values[:60] + [95.0] * 30
        cutoff = T0 + timedelta(minutes=59)
        early = [p for p in detect_anomalies(series(values)) if p.timestamp <= cutoff]
        early_changed = [p for p in detect_anomalies(series(changed)) if p.timestamp <= cutoff]
        self.assertEqual(early, early_changed)

    def test_warm_up_returns_no_baseline(self):
        self.assertEqual(causal_rolling_baseline([1.0, 2.0, 3.0], window=15, min_points=10), [None, None, None])


class DetectorTests(unittest.TestCase):
    def test_near_constant_series_has_no_anomalies(self):
        for amplitude in (0.0, 0.3):
            with self.subTest(amplitude=amplitude):
                values = [45 + wobble(i, amplitude) for i in range(180)]
                self.assertEqual(detect_anomalies(series(values)), [])

    def test_obvious_spike_is_detected(self):
        values = [100 + wobble(i, 2) for i in range(80)]
        values[50] = 400.0
        points = detect_anomalies(series(values, metric="latency_ms"))
        self.assertEqual(len(points), 1)
        spike = points[0]
        self.assertEqual((spike.timestamp, spike.metric_name, spike.service), (T0 + timedelta(minutes=50), "latency_ms", "orders-api"))
        self.assertEqual(spike.detection_method, DetectionMethod.ROLLING_ZSCORE)
        self.assertEqual(spike.direction, Direction.UP)
        self.assertAlmostEqual(spike.deviation, 400.0 - spike.baseline_mean)
        self.assertAlmostEqual(spike.z_score, spike.deviation / max(spike.baseline_std, 2.0))
        self.assertIs(spike.severity, AnomalySeverity.HIGH)

    def test_gradual_memory_increase_is_detected_and_stays_flagged(self):
        ramp_start = 40
        values = [45 + wobble(i, 0.2) for i in range(ramp_start)] + \
                 [45 + 0.4 * (k + 1) + wobble(ramp_start + k, 0.2) for k in range(80)]
        points = of_metric(detect_anomalies(series(values)), "memory_usage")
        self.assertTrue(points)
        first = min(p.timestamp for p in points)
        self.assertGreater(first, T0 + timedelta(minutes=ramp_start))
        self.assertLessEqual(first, T0 + timedelta(minutes=ramp_start + 20))
        self.assertTrue(all(p.direction == Direction.UP for p in points))
        # Flagged observations stay out of the baseline, so the rising level keeps being flagged.
        self.assertIn(T0 + timedelta(minutes=len(values) - 1), {p.timestamp for p in points})
        self.assertEqual(max(p.value for p in points), max(values))

    def test_plain_rolling_baseline_absorbs_a_sustained_shift(self):
        values = [45 + wobble(i, 0.3) for i in range(40)] + [70 + wobble(i, 0.3) for i in range(40)]
        excluding = of_metric(detect_anomalies(series(values)), "memory_usage")
        # drift_lag=0 so only the recent rolling window is in play: without exclusion it tracks
        # the new level and the shift stops looking anomalous after a few minutes.
        plain = of_metric(detect_anomalies(series(values), DetectorConfig(
            exclude_anomalies_from_baseline=False, drift_lag=0)), "memory_usage")
        self.assertEqual(len(excluding), 40)
        self.assertLess(len(plain), 5)

    def test_none_values_are_skipped(self):
        values = [None if i % 3 == 0 else 40 + wobble(i, 0.5) for i in range(60)]
        values[46] = 95.0
        points = detect_anomalies(series(values, metric="db_connection_utilization"))
        self.assertEqual([p.timestamp for p in points], [T0 + timedelta(minutes=46)])
        self.assertTrue(all(p.value is not None for p in points))
        # The baseline counts only the non-blank observations before minute 46.
        self.assertEqual(points[0].baseline_points, 15)
        self.assertEqual(detect_anomalies(series([None] * 30, metric="downstream_latency_ms")), [])

    def test_zero_standard_deviation_is_safe(self):
        self.assertEqual(zscore(55.0, BaselineStats(mean=50.0, std=0.0, count=15), min_std=0.25), 20.0)
        values = [50.0] * 30 + [50.0, 70.0, 50.0]
        points = detect_anomalies(series(values))
        self.assertEqual([p.timestamp for p in points], [T0 + timedelta(minutes=31)])
        self.assertEqual(points[0].baseline_std, 0.0)
        self.assertTrue(math.isfinite(points[0].z_score))

    def test_small_deviation_on_a_stable_series_is_not_flagged(self):
        # |z| far above the threshold, but a 0.5 pp change in error rate is below the practical floor.
        values = [0.3] * 30 + [0.8] * 5
        self.assertEqual(detect_anomalies(series(values, metric="error_rate")), [])

    def test_absolute_threshold_flags_saturation_during_warm_up(self):
        points = detect_anomalies(series([95.0] * 5, metric="db_connection_utilization"))
        self.assertEqual(len(points), 5)
        self.assertTrue(all(p.detection_method == DetectionMethod.ABSOLUTE_THRESHOLD and p.z_score is None
                            for p in points))
        self.assertTrue(all(p.severity is AnomalySeverity.MEDIUM for p in points))

    def test_metric_rules_are_configurable(self):
        values = [100 + wobble(i, 2) for i in range(40)]
        values[30] = 20.0
        down_spike = series(values, metric="latency_ms")
        self.assertEqual(len(detect_anomalies(down_spike)), 1)
        rules = {**DetectorConfig().metrics, "latency_ms": MetricRule(min_std=2.0, directions=(Direction.UP,))}
        self.assertEqual(detect_anomalies(down_spike, DetectorConfig(metrics=rules)), [])
        disabled = {**DetectorConfig().metrics, "latency_ms": MetricRule(min_std=2.0, enabled=False)}
        self.assertEqual(detect_anomalies(down_spike, DetectorConfig(metrics=disabled)), [])

    def test_invalid_configuration_is_rejected(self):
        with self.assertRaises(ValueError):
            DetectorConfig(baseline_window=5, min_baseline_points=10)
        with self.assertRaises(ValueError):
            DetectorConfig(metrics={"heap_bytes": MetricRule(min_std=1.0)})


class SeverityTests(unittest.TestCase):
    def test_severity_mapping_uses_absolute_z(self):
        thresholds = SeverityThresholds()
        cases = {3.0: "LOW", 9.99: "LOW", 10.0: "MEDIUM", -25.0: "MEDIUM", 49.9: "MEDIUM", 50.0: "HIGH", -400.0: "HIGH"}
        for z, expected in cases.items():
            with self.subTest(z=z):
                self.assertIs(severity_for_z(z, thresholds), AnomalySeverity(expected))

    def test_severity_thresholds_are_configurable(self):
        custom = SeverityThresholds(medium=4.0, high=6.0)
        self.assertIs(severity_for_z(5.0, custom), AnomalySeverity.MEDIUM)
        self.assertIs(severity_for_z(6.5, custom), AnomalySeverity.HIGH)
        with self.assertRaises(ValueError):
            SeverityThresholds(medium=10.0, high=10.0)


class WindowTests(unittest.TestCase):
    def test_consecutive_points_form_one_window(self):
        latency = [100 + wobble(i, 2) for i in range(60)]
        errors = [0.3 + wobble(i, 0.05) for i in range(60)]
        for i in range(40, 45):
            latency[i] = 900.0
            errors[i] = 12.0
        points = detect_anomalies(series(latency, metric="latency_ms", service="payment-api")
                                  + series(errors, metric="error_rate", service="orders-api"))
        windows = build_anomaly_windows(points)
        self.assertEqual(len(windows), 1)
        window = windows[0]
        self.assertEqual((window.start_time, window.end_time), (T0 + timedelta(minutes=40), T0 + timedelta(minutes=44)))
        self.assertEqual(window.duration_minutes, 4.0)
        self.assertEqual(window.anomaly_count, 10)
        self.assertEqual(window.affected_services, ("orders-api", "payment-api"))
        self.assertEqual(window.affected_metrics, ("error_rate", "latency_ms"))
        self.assertEqual(window.affected_series, ("orders-api:error_rate", "payment-api:latency_ms"))
        strongest = max(points, key=lambda p: abs(p.z_score))
        self.assertEqual((window.peak_metric, window.peak_service, window.peak_timestamp),
                         (strongest.metric_name, strongest.service, strongest.timestamp))
        self.assertAlmostEqual(window.peak_deviation, abs(strongest.z_score))
        self.assertIs(window.severity, max((p.severity for p in points), key=lambda s: s.rank))

    def test_gap_splits_windows(self):
        values = [100 + wobble(i, 2) for i in range(80)]
        for i in (30, 32, 36):  # gaps of 2 min (merged) and 4 min (split)
            values[i] = 500.0
        points = detect_anomalies(series(values, metric="latency_ms"))
        windows = build_anomaly_windows(points, max_gap_minutes=2)
        self.assertEqual([(w.start_time.minute, w.end_time.minute, w.anomaly_count) for w in windows], [(30, 32, 2), (36, 36, 1)])
        self.assertEqual(windows[1].duration_minutes, 0.0)
        self.assertEqual(len(build_anomaly_windows(points, max_gap_minutes=5)), 1)

    def test_windows_never_mix_incidents(self):
        a = series([100.0] * 20 + [900.0], metric="latency_ms", incident_id="INC-901")
        b = series([100.0] * 20 + [900.0], metric="latency_ms", incident_id="INC-902")
        windows = build_anomaly_windows(detect_anomalies(a + b))
        self.assertEqual(sorted(w.incident_id for w in windows), ["INC-901", "INC-902"])

    def test_no_points_no_windows(self):
        self.assertEqual(build_anomaly_windows([]), [])


class NoGroundTruthTests(unittest.TestCase):
    def test_result_models_have_no_root_cause_fields(self):
        forbidden = LEAKAGE_FIELDS | {"root_cause"}
        for model in (AnomalyPoint, AnomalyWindow, IncidentAnomalyReport, DetectorConfig):
            with self.subTest(model=model.__name__):
                self.assertFalse(forbidden & set(model.model_fields))

    def test_detection_code_never_touches_ground_truth(self):
        forbidden = ("load_ground_truth", "load_evaluation_record", "IncidentGroundTruth", "IncidentEvaluationRecord",
                     *sorted(LEAKAGE_FIELDS))
        for path in sorted((ROOT / "src" / "detection").glob("*.py")):
            source = path.read_text(encoding="utf-8")
            for name in forbidden:
                with self.subTest(file=path.name, name=name):
                    self.assertNotIn(name, source)

    def test_detector_runs_on_an_evidence_bundle_and_output_has_no_ground_truth(self):
        bundle = load_evidence_bundle("INC-011")
        report = detect_incident(bundle)
        self.assertEqual(report.incident_id, "INC-011")
        self.assertEqual(report.series_analyzed, 39)  # 6 services x 7 metrics minus the 3 that do not apply
        dumped = report.model_dump(mode="json")
        keys = set(dumped) | {k for p in dumped["points"] for k in p} | {k for w in dumped["windows"] for k in w}
        self.assertFalse(LEAKAGE_FIELDS & keys)
        text = report.model_dump_json()
        for label in ("DB_CONNECTION_POOL_EXHAUSTION", "MEMORY_LEAK", "DOWNSTREAM_SERVICE_TIMEOUT", "connection_leak"):
            self.assertNotIn(label, text)


class RealDatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_evidence_bundle("INC-011")
        cls.report = detect_incident(cls.bundle)

    def test_detection_is_deterministic(self):
        self.assertEqual(detect_incident(self.bundle), self.report)

    def test_points_are_consistent_with_their_observations(self):
        by_key = {(m.timestamp, m.service): m for m in self.bundle.metrics}
        for p in self.report.points:
            self.assertEqual(getattr(by_key[(p.timestamp, p.service)], p.metric_name), p.value)
            self.assertEqual(p.incident_id, "INC-011")

    def test_alert_period_contains_anomalies(self):
        ctx = self.bundle.context
        overlapping = [w for w in self.report.windows if w.start_time <= ctx.end_time and w.end_time >= ctx.start_time]
        self.assertTrue(overlapping)
        self.assertEqual(sum(w.anomaly_count for w in self.report.windows), len(self.report.points))


if __name__ == "__main__":
    unittest.main()
