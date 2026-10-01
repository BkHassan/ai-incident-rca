#!/usr/bin/env python3
"""Sanity check of the Day 5 anomaly detector. It is not an accuracy evaluation.

    python analysis/detection_sanity.py

The detector runs without ground truth. This script loads ground truth afterwards, only to
group its output: NORMAL cases, the minutes before each fault, and the incident period from
fault start to end_time. It compares the default configuration with a plain rolling baseline
and writes analysis/results/detection_sanity.json.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from detection import DetectorConfig, detect_incident  # noqa: E402
from ingestion import METRIC_FIELDS, incident_path, list_incident_ids, load_evidence_bundle, load_ground_truth  # noqa: E402

OUT = ROOT / "analysis" / "results" / "detection_sanity.json"
CONFIGS = {
    "default (drift check, anomalies excluded from baseline)": DetectorConfig(),
    "no drift check (drift_lag=0)": DetectorConfig(drift_lag=0),
    "plain shifted rolling baseline (no drift check, no exclusion)":
        DetectorConfig(drift_lag=0, exclude_anomalies_from_baseline=False),
}


def observations_before(bundle, cutoff) -> int:
    return sum(getattr(m, f) is not None for m in bundle.metrics if m.timestamp < cutoff for f in METRIC_FIELDS)


def rate(points: int, observations: int) -> float:
    return round(1000 * points / observations, 3) if observations else 0.0


def analyze(config: DetectorConfig, bundles: dict, truth: dict) -> dict:
    by_metric, by_severity, by_method = Counter(), Counter(), Counter()
    after_end = Counter()
    per_series = Counter()
    normal = {"cases": 0, "points": 0, "windows": 0, "high_points": 0, "observations": 0,
              "points_in_alert_window": 0, "per_case": {}}
    prefault = {"points": 0, "observations": 0}
    failure = {"cases": 0, "with_window_in_fault_period": 0, "alert_minutes": 0, "alert_minutes_with_anomaly": 0,
               "without_anomaly_in_fault_period": []}
    fault_period_metrics: dict[str, Counter] = {}
    totals = Counter()
    for iid, bundle in bundles.items():
        report = detect_incident(bundle, config)
        gt, ctx = truth[iid], bundle.context
        totals.update(points=len(report.points), windows=len(report.windows), observations=report.observations_analyzed,
                      incidents=1, incidents_with_anomaly=bool(report.points))
        for p in report.points:
            by_metric[p.metric_name] += 1
            by_severity[p.severity.value] += 1
            by_method[p.detection_method.value] += 1
            per_series[(iid, p.series)] += 1
            if p.timestamp > ctx.end_time:
                after_end[f"{p.metric_name}:{p.direction.value if p.direction else 'none'}"] += 1
        if gt.scenario == "NORMAL":
            normal["cases"] += 1
            normal["points"] += len(report.points)
            normal["windows"] += len(report.windows)
            normal["high_points"] += sum(p.severity == "HIGH" for p in report.points)
            normal["observations"] += report.observations_analyzed
            normal["points_in_alert_window"] += sum(ctx.start_time <= p.timestamp <= ctx.end_time for p in report.points)
            normal["per_case"][iid] = {"points": len(report.points), "windows": len(report.windows),
                                       "metrics": dict(Counter(p.metric_name for p in report.points))}
            continue
        failure["cases"] += 1
        prefault["points"] += sum(p.timestamp < gt.fault_start_time for p in report.points)
        prefault["observations"] += observations_before(bundle, gt.fault_start_time)
        in_period = [p for p in report.points if gt.fault_start_time <= p.timestamp <= ctx.end_time]
        if any(w.start_time <= ctx.end_time and w.end_time >= gt.fault_start_time for w in report.windows):
            failure["with_window_in_fault_period"] += 1
        else:
            failure["without_anomaly_in_fault_period"].append(iid)
        minutes = sorted({m.timestamp for m in bundle.metrics if ctx.start_time <= m.timestamp <= ctx.end_time})
        flagged = {p.timestamp for p in report.points}
        failure["alert_minutes"] += len(minutes)
        failure["alert_minutes_with_anomaly"] += sum(t in flagged for t in minutes)
        fault_period_metrics.setdefault(gt.scenario, Counter()).update(p.metric_name for p in in_period)

    total_points = totals["points"] or 1
    top_series = per_series.most_common(5)
    series_lengths = {}
    for iid, bundle in bundles.items():
        for m in bundle.metrics:
            for f in METRIC_FIELDS:
                if getattr(m, f) is not None:
                    series_lengths[(iid, f"{m.service}:{f}")] = series_lengths.get((iid, f"{m.service}:{f}"), 0) + 1
    return {
        "incidents": totals["incidents"],
        "points": totals["points"],
        "windows": totals["windows"],
        "observations": totals["observations"],
        "incidents_with_anomaly": totals["incidents_with_anomaly"],
        "points_by_metric": dict(by_metric.most_common()),
        "largest_metric_share": round(max(by_metric.values(), default=0) / total_points, 3),
        "points_by_severity": dict(by_severity),
        "points_by_method": dict(by_method),
        "points_after_alert_end_by_metric_direction": dict(after_end.most_common()),
        "top_series": [{"incident_id": i, "series": s, "points": n,
                        "share_of_series": round(n / series_lengths[(i, s)], 3)} for (i, s), n in top_series],
        "normal": {**normal, "rate_per_1000_observations": rate(normal["points"], normal["observations"])},
        "failure_pre_fault": {**prefault, "rate_per_1000_observations": rate(prefault["points"], prefault["observations"])},
        "failure_fault_period": {
            **failure,
            "share_of_alert_minutes_with_anomaly": round(failure["alert_minutes_with_anomaly"] / failure["alert_minutes"], 3),
        },
        "fault_period_points_by_scenario_and_metric": {s: dict(c.most_common()) for s, c in sorted(fault_period_metrics.items())},
    }


def main() -> int:
    ids = list_incident_ids()
    bundles = {iid: load_evidence_bundle(iid) for iid in ids}
    truth = {iid: load_ground_truth(incident_path(iid)) for iid in ids}  # used only to group results
    results = {name: analyze(config, bundles, truth) for name, config in CONFIGS.items()}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(results, indent=1, default=str) + "\n", encoding="utf-8")
    for name, r in results.items():
        n, pre, fp = r["normal"], r["failure_pre_fault"], r["failure_fault_period"]
        print(f"== {name}")
        print(f"  points {r['points']}, windows {r['windows']}, incidents with anomalies {r['incidents_with_anomaly']}/{r['incidents']}")
        print(f"  by metric {r['points_by_metric']} (largest share {r['largest_metric_share']})")
        print(f"  by severity {r['points_by_severity']}; by method {r['points_by_method']}")
        print(f"  after alert end_time {r['points_after_alert_end_by_metric_direction']}")
        print(f"  NORMAL: {n['points']} points, {n['windows']} windows, {n['high_points']} HIGH, "
              f"{n['rate_per_1000_observations']} per 1000 observations; {n['points_in_alert_window']} inside the alert window")
        for iid, c in n["per_case"].items():
            print(f"    {iid}: {c}")
        print(f"  failures before fault start: {pre['points']} points, {pre['rate_per_1000_observations']} per 1000 observations")
        print(f"  failures with a window in fault..end: {fp['with_window_in_fault_period']}/{fp['cases']}; "
              f"alert minutes with an anomaly {fp['share_of_alert_minutes_with_anomaly']}")
        print(f"  top series {r['top_series'][:3]}")
        for scenario, counts in r["fault_period_points_by_scenario_and_metric"].items():
            print(f"    fault period {scenario}: {counts}")
    print(f"\nwritten {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
