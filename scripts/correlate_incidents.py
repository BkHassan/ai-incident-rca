#!/usr/bin/env python3
"""Build observational timelines for every ingested incident.

    python scripts/correlate_incidents.py [--data-dir data] [--anomalies-dir data/derived/anomalies]
                                          [--output-dir data/derived/correlation]

Loads IncidentEvidenceBundle (no ground truth) and Day 5 anomaly JSON, writes one correlation
file per incident, then prints a summary. A separate sanity block may load ground truth only
after correlation, to compare NORMAL vs failure timeline sizes.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from correlation import DEFAULT_CONFIG, correlate_incident  # noqa: E402
from correlation.models import IncidentTimeline, SourceType  # noqa: E402
from detection.models import IncidentAnomalyReport  # noqa: E402
from ingestion import (  # noqa: E402
    DEFAULT_DATA_DIR,
    incident_path,
    list_incident_ids,
    load_evidence_bundle,
    load_ground_truth,
)

DEFAULT_ANOMALIES = DEFAULT_DATA_DIR / "derived" / "anomalies"
DEFAULT_OUTPUT = DEFAULT_DATA_DIR / "derived" / "correlation"
LEAKAGE = ("true_root_cause", "scenario", "root_cause_service", "root_cause_variant",
           "root_cause_detail", "fault_start_time", "expected_symptoms", "resolution")
CAUSAL = (" caused ", " causing ", " because ", " due to ", " led to ", " root cause")


def load_anomaly_report(anomalies_dir: Path, incident_id: str) -> IncidentAnomalyReport:
    path = anomalies_dir / f"{incident_id}.json"
    return IncidentAnomalyReport.model_validate_json(path.read_text(encoding="utf-8"))


def write_timeline(timeline: IncidentTimeline, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{timeline.incident_id}.json"
    path.write_text(timeline.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path


def contains_leakage(timeline: IncidentTimeline) -> list[str]:
    dumped = timeline.model_dump(mode="json")
    keys = set(dumped)
    keys |= {k for event in dumped["events"] for k in event}
    keys |= {k for item in dumped["evidence_items"] for k in item}
    return sorted(k for k in keys if k in LEAKAGE)


def contains_causal_language(timeline: IncidentTimeline) -> list[str]:
    hits = []
    for event in timeline.events:
        blob = f" {event.title.lower()} "
        for phrase in CAUSAL:
            if phrase in blob:
                hits.append(f"{event.evidence_id}: {phrase.strip()}")
    return hits


def print_timeline(timeline: IncidentTimeline, limit: int = 12) -> None:
    print(f"{timeline.incident_id}  alert {timeline.start_time} -> {timeline.end_time}  "
          f"services={list(timeline.involved_services)}")
    print(f"  events={len(timeline.events)}  evidence={len(timeline.evidence_items)}  "
          f"windows={len(timeline.anomaly_windows)}")
    first = timeline.first_observed_event
    if first is None:
        print("  first observed event: none")
        return
    print(f"  first observed: {first.timestamp}  {first.title}  [{first.evidence_id}]")
    for event in timeline.events[:limit]:
        print(f"    {event.timestamp}  {event.title}")
    if len(timeline.events) > limit:
        print(f"    ... {len(timeline.events) - limit} more")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--anomalies-dir", type=Path, default=DEFAULT_ANOMALIES)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    ids = list_incident_ids(args.data_dir)
    print(f"Config: lookback={DEFAULT_CONFIG.lookback_minutes}m  after={DEFAULT_CONFIG.after_pad_minutes}m  "
          f"change_lookback={DEFAULT_CONFIG.change_lookback_minutes}m  "
          f"link={DEFAULT_CONFIG.log_to_window_link_minutes}m")
    print(f"\n== Correlating {len(ids)} incidents ==")
    timelines: list[IncidentTimeline] = []
    failures: list[str] = []
    started = time.perf_counter()
    for incident_id in ids:
        try:
            bundle = load_evidence_bundle(incident_id, args.data_dir)
            anomalies = load_anomaly_report(args.anomalies_dir, incident_id)
            timeline = correlate_incident(bundle, anomalies)
            leaks = contains_leakage(timeline)
            causal = contains_causal_language(timeline)
            if leaks:
                failures.append(f"{incident_id}: leaked fields {leaks}")
            if causal:
                failures.append(f"{incident_id}: causal language {causal}")
            write_timeline(timeline, args.output_dir)
            timelines.append(timeline)
            print(f"  {incident_id}: {len(timeline.events)} events, {len(timeline.evidence_items)} evidence, "
                  f"{len(timeline.involved_services)} services")
        except Exception as exc:  # noqa: BLE001 — report and continue so one bad case is visible
            failures.append(f"{incident_id}: {exc}")
            print(f"  {incident_id}: FAIL {exc}")
    elapsed = time.perf_counter() - started

    n_events = sum(len(t.events) for t in timelines)
    n_evidence = sum(len(t.evidence_items) for t in timelines)
    empty = [t.incident_id for t in timelines if not t.events]
    services = Counter(s for t in timelines for s in t.involved_services)
    by_source = Counter(e.source_type.value for t in timelines for e in t.events)
    print(f"Wrote {len(timelines)} files to {args.output_dir} in {elapsed:.1f}s")
    print("\n== Summary ==")
    print(f"Incidents processed: {len(ids)}")
    print(f"Incidents successfully correlated: {len(timelines)}")
    print(f"Incidents with no relevant events: {len(empty)}" + (f" ({', '.join(empty)})" if empty else ""))
    print(f"Total timeline events: {n_events}")
    print(f"Total evidence items: {n_evidence}")
    if timelines:
        print(f"Average timeline length: {n_events / len(timelines):.1f}")
        print(f"Average evidence items per incident: {n_evidence / len(timelines):.1f}")
    print("Timeline events by source:", dict(by_source))
    print("Services represented:", ", ".join(f"{s} ({n})" for s, n in services.most_common()))
    print(f"Failures: {len(failures)}")
    for failure in failures:
        print("  - " + failure)

    print("\n== Sanity (ground truth loaded separately, not used by correlation) ==")
    for timeline in timelines:
        truth = load_ground_truth(incident_path(timeline.incident_id, args.data_dir))
        kind = "NORMAL" if truth.scenario == "NORMAL" else "FAILURE"
        ordered = all(a.timestamp <= b.timestamp for a, b in zip(timeline.events, timeline.events[1:]))
        print(f"  {timeline.incident_id} {kind}: {len(timeline.events)} events  ordered={ordered}")
    normals = [t for t in timelines
               if load_ground_truth(incident_path(t.incident_id, args.data_dir)).scenario == "NORMAL"]
    failures_t = [t for t in timelines if t not in normals]
    if normals and failures_t:
        n_max = max(len(t.events) for t in normals)
        f_min = min(len(t.events) for t in failures_t)
        print(f"NORMAL max timeline length: {n_max}; FAILURE min: {f_min}")

    print("\n== Representative timelines ==")
    examples = {"INC-011": "DB pool (payment-api)", "INC-034": "memory leak (orders-api)",
                "INC-001": "downstream timeout (orders-api)", "INC-014": "NORMAL (inventory-service)"}
    by_id = {t.incident_id: t for t in timelines}
    for incident_id, label in examples.items():
        if incident_id in by_id:
            print(f"\n{label}")
            print_timeline(by_id[incident_id])
    return 1 if failures or len(timelines) != len(ids) else 0


if __name__ == "__main__":
    sys.exit(main())
