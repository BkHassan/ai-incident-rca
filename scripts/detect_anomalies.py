#!/usr/bin/env python3
"""Run the statistical detector on every ingested incident and write derived anomaly files.

    python scripts/detect_anomalies.py [--data-dir data] [--output-dir data/derived/anomalies]

Loads each incident through ``load_evidence_bundle`` (no ground truth), runs the detector, and
writes one JSON file per incident. A post-hoc sanity block then loads ground truth separately so
NORMAL vs failure counts can be inspected without feeding labels into detection.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from detection import DEFAULT_CONFIG, detect_incident  # noqa: E402
from detection.models import DETECTOR_NAME, DETECTOR_VERSION, DetectorConfig, IncidentAnomalyReport  # noqa: E402
from ingestion import (  # noqa: E402
    DEFAULT_DATA_DIR,
    incident_path,
    list_incident_ids,
    load_evidence_bundle,
    load_ground_truth,
    load_incident_context,
)

DEFAULT_OUTPUT = DEFAULT_DATA_DIR / "derived" / "anomalies"


def write_report(report: IncidentAnomalyReport, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{report.incident_id}.json"
    path.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def print_config(config: DetectorConfig) -> None:
    print("Detector:", DETECTOR_NAME, DETECTOR_VERSION)
    print(f"  baseline_window={config.baseline_window}  min_baseline_points={config.min_baseline_points}  "
          f"z_threshold={config.z_threshold}  drift_lag={config.drift_lag}")
    print(f"  exclude_anomalies_from_baseline={config.exclude_anomalies_from_baseline}  "
          f"window_max_gap_minutes={config.window_max_gap_minutes}")
    print(f"  severity |z|: LOW < {config.severity.medium} <= MEDIUM < {config.severity.high} <= HIGH "
          "(MVP heuristics, not an industry standard)")
    print("  metric rules:")
    for name, rule in config.metrics.items():
        parts = [f"min_std={rule.min_std}"]
        if rule.min_abs_deviation:
            parts.append(f"min_abs_dev={rule.min_abs_deviation}")
        if rule.min_rel_deviation:
            parts.append(f"min_rel_dev={rule.min_rel_deviation}")
        if rule.absolute_threshold is not None:
            parts.append(f"abs_threshold={rule.absolute_threshold}")
        print(f"    {name}: " + ", ".join(parts))


def print_summary(reports: list[IncidentAnomalyReport]) -> None:
    by_metric, by_severity, by_method, by_incident = Counter(), Counter(), Counter(), Counter()
    for report in reports:
        by_incident[report.incident_id] = len(report.points)
        for point in report.points:
            by_metric[point.metric_name] += 1
            by_severity[point.severity.value] += 1
            by_method[point.detection_method.value] += 1
    total_points = sum(by_incident.values())
    total_windows = sum(len(r.windows) for r in reports)
    with_anomalies = sum(1 for n in by_incident.values() if n)
    print(f"Incidents processed: {len(reports)}")
    print(f"Anomaly points: {total_points}")
    print(f"Anomaly windows: {total_windows}")
    print(f"Incidents with at least one anomaly: {with_anomalies}")
    print(f"Incidents with no anomalies: {len(reports) - with_anomalies}")
    print("Anomaly points by metric:")
    for name, n in by_metric.most_common():
        print(f"  {name}: {n}")
    print("Anomaly points by severity:")
    for name in ("LOW", "MEDIUM", "HIGH"):
        print(f"  {name}: {by_severity[name]}")
    print("Anomaly points by detection method:")
    for name, n in by_method.most_common():
        print(f"  {name}: {n}")


def print_sanity(reports: list[IncidentAnomalyReport], data_dir: Path) -> None:
    """Inspect detection output against ground truth. Labels are loaded only here, after detection."""
    print("\n== Sanity (ground truth loaded separately, not used by the detector) ==")
    by_kind = {"NORMAL": [], "FAILURE": []}
    quiet_failures = []
    noisy_normals = []
    for report in reports:
        truth = load_ground_truth(incident_path(report.incident_id, data_dir))
        kind = "NORMAL" if truth.scenario == "NORMAL" else "FAILURE"
        by_kind[kind].append(report)
        context = load_incident_context(incident_path(report.incident_id, data_dir))
        overlapping = [w for w in report.windows
                       if w.start_time <= context.end_time and w.end_time >= context.start_time]
        if kind == "FAILURE" and not overlapping:
            quiet_failures.append(report.incident_id)
        if kind == "NORMAL" and len(report.points) > 200:
            noisy_normals.append((report.incident_id, len(report.points), len(report.windows)))

    def describe(label: str, group: list[IncidentAnomalyReport]) -> None:
        if not group:
            print(f"{label}: none")
            return
        points = [len(r.points) for r in group]
        windows = [len(r.windows) for r in group]
        print(f"{label} ({len(group)}): "
              f"points min/median/max={min(points)}/{sorted(points)[len(points)//2]}/{max(points)}  "
              f"windows min/median/max={min(windows)}/{sorted(windows)[len(windows)//2]}/{max(windows)}")
        for report in sorted(group, key=lambda r: r.incident_id):
            print(f"  {report.incident_id}: {len(report.points)} points, {len(report.windows)} windows")

    describe("NORMAL", by_kind["NORMAL"])
    describe("FAILURE", by_kind["FAILURE"])
    if quiet_failures:
        print("Failures with no anomaly window overlapping the alert period:", ", ".join(quiet_failures))
    else:
        print("Every failure has at least one anomaly window overlapping the alert period.")
    if noisy_normals:
        print("NORMAL cases with >200 anomaly points:", noisy_normals)
    else:
        print("No NORMAL case exceeded 200 anomaly points.")


def print_example(report: IncidentAnomalyReport) -> None:
    if not report.points:
        print(f"Representative {report.incident_id}: no anomaly points")
        return
    peak = max(report.points, key=lambda p: abs(p.z_score) if p.z_score is not None else -1.0)
    print(f"Representative {report.incident_id}: {len(report.points)} points, {len(report.windows)} windows")
    print(f"  peak: {peak.service} {peak.metric_name}={peak.value:.1f} at {peak.timestamp}  "
          f"z={peak.z_score:.1f}  baseline={peak.baseline_mean:.1f}+/-{peak.baseline_std:.1f}  "
          f"{peak.severity.value} {peak.detection_method.value}")
    window = max(report.windows, key=lambda w: w.anomaly_count)
    print(f"  largest window: {window.start_time} -> {window.end_time} ({window.duration_minutes:.1f} min)  "
          f"{window.anomaly_count} points  peak {window.peak_service}:{window.peak_metric}  "
          f"services={list(window.affected_services)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--example", default="INC-011")
    args = parser.parse_args()

    print_config(DEFAULT_CONFIG)
    ids = list_incident_ids(args.data_dir)
    print(f"\n== Detecting {len(ids)} incidents ==")
    reports = []
    started = time.perf_counter()
    for incident_id in ids:
        report = detect_incident(load_evidence_bundle(incident_id, args.data_dir))
        write_report(report, args.output_dir)
        reports.append(report)
        print(f"  {incident_id}: {len(report.points)} points, {len(report.windows)} windows")
    elapsed = time.perf_counter() - started
    print(f"Wrote {len(reports)} files to {args.output_dir} in {elapsed:.1f}s")
    print("\n== Summary ==")
    print_summary(reports)
    print_sanity(reports, args.data_dir)
    example = next((r for r in reports if r.incident_id == args.example), reports[0])
    print("\n== Example ==")
    print_example(example)
    return 0


if __name__ == "__main__":
    sys.exit(main())
