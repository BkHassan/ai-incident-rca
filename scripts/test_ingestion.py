#!/usr/bin/env python3
"""Ingestion smoke test: load one incident in detail, then every incident in the dataset.

    python scripts/test_ingestion.py [--incident INC-011] [--data-dir data]

Prints a summary of the representative evidence bundle (without its root cause), then checks
that every incident, log and metric file loads, that IDs link up, and that ground truth stays
out of the evidence bundles. Exits non-zero on any failure.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ingestion import (  # noqa: E402
    DEFAULT_DATA_DIR,
    GROUND_TRUTH_FIELDS,
    EventType,
    IncidentEvidenceBundle,
    IngestionError,
    incident_path,
    list_incident_ids,
    load_evidence_bundle,
    load_ground_truth,
)

GROUND_TRUTH_ONLY = frozenset(GROUND_TRUTH_FIELDS) - {"incident_id"}


def contains_ground_truth(bundle: IncidentEvidenceBundle) -> bool:
    dumped = bundle.model_dump()
    keys = set(IncidentEvidenceBundle.model_fields) | set(dumped["context"])
    keys |= {k for record in dumped["logs"] + dumped["metrics"] for k in record}
    return bool(keys & GROUND_TRUTH_ONLY)


def summarize(incident_id: str, data_dir: Path) -> bool:
    bundle = load_evidence_bundle(incident_id, data_dir)
    truth = load_ground_truth(incident_path(incident_id, data_dir))
    ctx = bundle.context
    levels = Counter(e.level.value for e in bundle.logs)
    events = Counter(e.event_type.value for e in bundle.logs)
    services = sorted({m.service for m in bundle.metrics})
    leaked = contains_ground_truth(bundle)
    print(f"Incident: {ctx.incident_id}")
    print(f"Title: {ctx.title}")
    print(f"Service: {ctx.service}")
    print(f"Severity: {ctx.severity.value}")
    print(f"Alert: {ctx.start_time} -> {ctx.end_time} ({ctx.duration_minutes} min)")
    print(f"Logs: {len(bundle.logs)} (" + ", ".join(f"{lvl} {levels[lvl]}" for lvl in ("INFO", "WARN", "ERROR")) + ")")
    print(f"  first {bundle.logs[0].timestamp}, last {bundle.logs[-1].timestamp}")
    print("  top event types: " + ", ".join(f"{name} {n}" for name, n in events.most_common(6)))
    print(f"Metric points: {len(bundle.metrics)} ({len(services)} services x "
          f"{len({m.timestamp for m in bundle.metrics})} minutes)")
    print(f"Evidence bundle fields: {', '.join(IncidentEvidenceBundle.model_fields)}")
    print(f"Evidence bundle contains ground truth: {'YES' if leaked else 'NO'}")
    print(f"Ground truth loaded separately: {'YES' if truth.incident_id == ctx.incident_id else 'NO'} "
          f"({len(type(truth).model_fields)} fields, not printed)")
    return not leaked


def full_check(data_dir: Path) -> bool:
    raw = data_dir / "raw"
    manifest = json.loads((data_dir / "generated" / "manifest.json").read_text(encoding="utf-8"))
    ids = list_incident_ids(data_dir)
    failures: list[str] = []
    built = logs = metrics = unknown = truths = 0
    levels, scenarios = Counter(), Counter()
    started = time.perf_counter()
    for incident_id in ids:
        try:
            bundle = load_evidence_bundle(incident_id, data_dir)
            built += 1
            truth = load_ground_truth(incident_path(incident_id, data_dir))
        except (IngestionError, OSError) as exc:
            failures.append(str(exc))
            continue
        if contains_ground_truth(bundle):
            failures.append(f"{incident_id}: evidence bundle exposes ground-truth fields")
        logs += len(bundle.logs)
        metrics += len(bundle.metrics)
        levels.update(e.level.value for e in bundle.logs)
        unknown += sum(e.event_type is EventType.UNKNOWN for e in bundle.logs)
        truths += 1
        scenarios[truth.scenario] += 1
    elapsed = time.perf_counter() - started

    orphans = sorted({p.stem for sub in ("logs", "metrics") for p in (raw / sub).iterdir()} - set(ids))
    if orphans:
        failures.append(f"log/metric files without incident metadata: {orphans}")
    if len(ids) != manifest["total_cases"]:
        failures.append(f"{len(ids)} incident files, manifest says {manifest['total_cases']}")
    if not failures:
        if logs != manifest["log_records"]:
            failures.append(f"parsed {logs} log records, manifest says {manifest['log_records']}")
        if metrics != manifest["metric_rows"]:
            failures.append(f"parsed {metrics} metric points, manifest says {manifest['metric_rows']}")

    print(f"Incidents found: {len(ids)} (manifest: {manifest['total_cases']})")
    print(f"Evidence bundles built: {built} of {len(ids)} in {elapsed:.1f}s")
    print(f"Log records parsed: {logs} (manifest: {manifest['log_records']}; "
          + ", ".join(f"{lvl} {levels[lvl]}" for lvl in ("INFO", "WARN", "ERROR")) + ")")
    print(f"Metric points parsed: {metrics} (manifest: {manifest['metric_rows']})")
    print(f"Log records with event_type 'unknown': {unknown}")
    print(f"Ground-truth records loaded separately: {truths} (" +
          ", ".join(f"{s} {n}" for s, n in sorted(scenarios.items())) + ")")
    print(f"Orphan log/metric files: {len(orphans)}")
    print(f"Failures: {len(failures)}")
    for failure in failures:
        print("  - " + failure.replace("\n", "\n    "))
    return not failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--incident", default="INC-011")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    args = parser.parse_args()
    print("== Representative incident ==")
    ok = summarize(args.incident, args.data_dir)
    print("\n== Full dataset ==")
    ok = full_check(args.data_dir) and ok
    print(f"\nResult: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
