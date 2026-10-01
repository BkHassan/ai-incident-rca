#!/usr/bin/env python3
"""Validate the synthetic incident dataset produced by generate_logs.py.

    python scripts/validate_dataset.py [--data-dir data]

Checks structure, linkage, ground truth, timestamps, metric columns, log
levels, scenario-consistent metric signatures, variation between incidents,
and that no single log template trivially identifies a scenario.
Exits with status 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import statistics
import sys
from datetime import datetime, timedelta
from pathlib import Path

FAILURE_SCENARIOS = ("DB_CONNECTION_POOL_EXHAUSTION", "MEMORY_LEAK", "DOWNSTREAM_SERVICE_TIMEOUT")
NORMAL = "NORMAL"
MIN_TOTAL, MIN_PER_FAILURE, MIN_NORMAL = 35, 10, 5

REQUIRED_INCIDENT_FIELDS = ("incident_id", "scenario", "service", "severity", "start_time", "end_time",
                            "window_start", "window_end", "description", "true_root_cause",
                            "expected_symptoms", "affected_services")
REQUIRED_LOG_FIELDS = ("timestamp", "service", "level", "message", "trace_id", "incident_id")
REQUIRED_METRIC_COLUMNS = ("timestamp", "incident_id", "service", "cpu_usage", "memory_usage", "request_rate",
                           "latency_ms", "error_rate", "db_connection_utilization", "downstream_latency_ms")
NUMERIC_COLUMNS = REQUIRED_METRIC_COLUMNS[3:]
NULLABLE_COLUMNS = {"db_connection_utilization", "downstream_latency_ms"}
PERCENT_COLUMNS = {"cpu_usage", "memory_usage", "error_rate", "db_connection_utilization"}
LEVELS = ("INFO", "WARN", "ERROR")
SEVERITIES = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
LABEL_LEAK = re.compile(r"DB_CONNECTION_POOL_EXHAUSTION|MEMORY_LEAK|DOWNSTREAM_SERVICE_TIMEOUT|"
                        r"root[ _-]?cause|memory leak|pool exhaust", re.IGNORECASE)


def normalize(message):
    """Collapse ids and numbers so messages can be compared as templates."""
    message = re.sub(r"(?=[0-9a-f]*\d)[0-9a-f]{5,}", "#", message)
    return re.sub(r"\d+(\.\d+)?", "#", message)


def parse_ts(value):
    return datetime.fromisoformat(value)


class Report:
    def __init__(self):
        self.results = []

    def check(self, name, problems_or_ok, detail=""):
        if isinstance(problems_or_ok, bool):
            ok, problems = problems_or_ok, ([detail] if detail and not problems_or_ok else [])
        else:
            problems = list(problems_or_ok)
            ok = not problems
        self.results.append((name, ok, problems, detail if ok else ""))
        return ok

    @property
    def ok(self):
        return all(ok for _, ok, _, _ in self.results)

    def print(self):
        for name, ok, problems, detail in self.results:
            suffix = f" ({detail})" if ok and detail else ""
            print(f"  [{'PASS' if ok else 'FAIL'}] {name}{suffix}")
            for problem in problems[:5]:
                print(f"         - {problem}")
            if len(problems) > 5:
                print(f"         - ... {len(problems) - 5} more")


def load_incidents(inc_dir, report):
    incidents, problems = {}, []
    for path in sorted(inc_dir.glob("*.json")):
        try:
            meta = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"{path.name}: unreadable ({exc})")
            continue
        missing = [k for k in REQUIRED_INCIDENT_FIELDS if k not in meta]
        if missing:
            problems.append(f"{path.name}: missing fields {missing}")
            continue
        if not meta["incident_id"]:
            problems.append(f"{path.name}: empty incident_id")
            continue
        if meta["incident_id"] != path.stem:
            problems.append(f"{path.name}: incident_id {meta['incident_id']!r} does not match file name")
        if meta["incident_id"] in incidents:
            problems.append(f"{path.name}: duplicate incident_id {meta['incident_id']}")
        if meta["severity"] not in SEVERITIES:
            problems.append(f"{path.name}: unknown severity {meta['severity']!r}")
        incidents[meta["incident_id"]] = meta
    report.check("incident metadata files are well-formed and have an incident_id", problems,
                 f"{len(incidents)} incidents")
    return incidents


def check_counts_and_ground_truth(incidents, report):
    counts = {s: 0 for s in FAILURE_SCENARIOS + (NORMAL,)}
    problems = []
    for iid, meta in incidents.items():
        scenario = meta["scenario"]
        if scenario not in counts:
            problems.append(f"{iid}: unknown scenario {scenario!r}")
            continue
        counts[scenario] += 1
        if scenario == NORMAL:
            if meta["true_root_cause"] is not None:
                problems.append(f"{iid}: NORMAL case must have null true_root_cause")
        elif meta["true_root_cause"] != scenario:
            problems.append(f"{iid}: true_root_cause {meta['true_root_cause']!r} should be {scenario}")
        if scenario != NORMAL and not meta["affected_services"]:
            problems.append(f"{iid}: failure incident without affected_services")
        if scenario != NORMAL and not meta["expected_symptoms"]:
            problems.append(f"{iid}: failure incident without expected_symptoms")
    total = sum(counts.values())
    report.check(f"at least {MIN_TOTAL} cases", total >= MIN_TOTAL, f"{total} cases")
    for scenario in FAILURE_SCENARIOS:
        report.check(f"at least {MIN_PER_FAILURE} {scenario} cases", counts[scenario] >= MIN_PER_FAILURE,
                     f"{counts[scenario]}")
    report.check(f"at least {MIN_NORMAL} NORMAL cases", counts[NORMAL] >= MIN_NORMAL, f"{counts[NORMAL]}")
    report.check("ground truth: failures have true_root_cause, NORMAL cases have null", problems)
    return counts


def check_incident_times(incidents, report):
    problems = []
    for iid, meta in incidents.items():
        try:
            ws, we = parse_ts(meta["window_start"]), parse_ts(meta["window_end"])
            st, et = parse_ts(meta["start_time"]), parse_ts(meta["end_time"])
            fault = parse_ts(meta["fault_start_time"]) if meta.get("fault_start_time") else None
        except (TypeError, ValueError) as exc:
            problems.append(f"{iid}: invalid timestamp ({exc})")
            continue
        if not (ws <= st < et <= we):
            problems.append(f"{iid}: expected window_start <= start_time < end_time <= window_end")
        if meta["scenario"] != NORMAL and (fault is None or not ws <= fault <= st):
            problems.append(f"{iid}: fault_start_time must lie between window_start and start_time")
        meta["_t"] = {"ws": ws, "we": we, "start": st, "end": et, "fault": fault}
    report.check("incident timestamps are valid and ordered", problems)


def check_logs(incidents, log_dir, report):
    problems, orphans = [], []
    level_totals = {lv: 0 for lv in LEVELS}
    stats = {}
    for iid, meta in incidents.items():
        path = log_dir / f"{iid}.jsonl"
        if not path.is_file():
            problems.append(f"{iid}: missing log file {path.name}")
            continue
        t = meta.get("_t")
        prev, levels, templates, n = None, {lv: 0 for lv in LEVELS}, {"ERROR": set(), "WARN": set()}, 0
        leaks = 0
        with path.open(encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                if not line.strip():
                    continue
                n += 1
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    problems.append(f"{path.name}:{lineno}: invalid JSON")
                    continue
                missing = [k for k in REQUIRED_LOG_FIELDS if k not in rec]
                if missing:
                    problems.append(f"{path.name}:{lineno}: missing fields {missing}")
                    continue
                if rec["incident_id"] != iid:
                    problems.append(f"{path.name}:{lineno}: incident_id {rec['incident_id']!r} != {iid}")
                if rec["incident_id"] not in incidents:
                    problems.append(f"{path.name}:{lineno}: unknown incident_id {rec['incident_id']!r}")
                if rec["level"] not in LEVELS:
                    problems.append(f"{path.name}:{lineno}: unknown level {rec['level']!r}")
                    continue
                if not rec["message"] or not rec["service"]:
                    problems.append(f"{path.name}:{lineno}: empty message or service")
                try:
                    ts = parse_ts(rec["timestamp"])
                except (TypeError, ValueError):
                    problems.append(f"{path.name}:{lineno}: invalid timestamp {rec['timestamp']!r}")
                    continue
                if prev is not None and ts < prev:
                    problems.append(f"{path.name}:{lineno}: timestamps not in order")
                prev = ts
                if t and not t["ws"] <= ts <= t["we"]:
                    problems.append(f"{path.name}:{lineno}: timestamp outside incident window")
                levels[rec["level"]] += 1
                if rec["level"] in templates:
                    templates[rec["level"]].add(normalize(rec["message"]))
                if LABEL_LEAK.search(rec["message"]):
                    leaks += 1
        if n == 0:
            problems.append(f"{path.name}: no log records")
        for lv in LEVELS:
            level_totals[lv] += levels[lv]
        stats[iid] = {"n": n, "levels": levels, "templates": templates, "leaks": leaks}
    known = set(incidents)
    orphans = [p.name for p in log_dir.glob("*.jsonl") if p.stem not in known]
    report.check("every case has a valid, ordered log file linked by incident_id", problems,
                 f"{sum(s['n'] for s in stats.values())} records")
    report.check("no log files reference unknown incidents", [f"orphan log file {o}" for o in orphans])
    return stats, level_totals


def check_metrics(incidents, met_dir, report):
    problems = []
    series = {}
    for iid, meta in incidents.items():
        path = met_dir / f"{iid}.csv"
        if not path.is_file():
            problems.append(f"{iid}: missing metrics file {path.name}")
            continue
        t = meta.get("_t")
        with path.open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            missing = [c for c in REQUIRED_METRIC_COLUMNS if c not in (reader.fieldnames or [])]
            if missing:
                problems.append(f"{path.name}: missing columns {missing}")
                continue
            per_service, prev_global, rows = {}, None, 0
            for lineno, row in enumerate(reader, 2):
                rows += 1
                if row["incident_id"] != iid or row["incident_id"] not in incidents:
                    problems.append(f"{path.name}:{lineno}: incident_id {row['incident_id']!r} not valid for this file")
                try:
                    ts = parse_ts(row["timestamp"])
                except (TypeError, ValueError):
                    problems.append(f"{path.name}:{lineno}: invalid timestamp")
                    continue
                if prev_global is not None and ts < prev_global:
                    problems.append(f"{path.name}:{lineno}: timestamps not in order")
                prev_global = ts
                if t and not t["ws"] <= ts <= t["we"]:
                    problems.append(f"{path.name}:{lineno}: timestamp outside incident window")
                svc = row["service"]
                values = {}
                for col in NUMERIC_COLUMNS:
                    raw = row[col]
                    if raw == "":
                        if col not in NULLABLE_COLUMNS:
                            problems.append(f"{path.name}:{lineno}: empty {col}")
                        values[col] = None
                        continue
                    try:
                        value = float(raw)
                    except ValueError:
                        problems.append(f"{path.name}:{lineno}: non-numeric {col}={raw!r}")
                        continue
                    if value < 0 or (col in PERCENT_COLUMNS and value > 100):
                        problems.append(f"{path.name}:{lineno}: {col}={value} out of range")
                    values[col] = value
                s = per_service.setdefault(svc, {"ts": [], **{c: [] for c in NUMERIC_COLUMNS}})
                if s["ts"] and ts <= s["ts"][-1]:
                    problems.append(f"{path.name}:{lineno}: {svc} timestamps not strictly increasing")
                s["ts"].append(ts)
                for col in NUMERIC_COLUMNS:
                    s[col].append(values.get(col))
            if rows == 0:
                problems.append(f"{path.name}: no metric rows")
        series[iid] = per_service
    orphans = [p.name for p in met_dir.glob("*.csv") if p.stem not in incidents]
    report.check("every case has a metrics file with all required columns, valid values and ordered timestamps",
                 problems, f"columns: {', '.join(REQUIRED_METRIC_COLUMNS[3:])}")
    report.check("no metric files reference unknown incidents", [f"orphan metrics file {o}" for o in orphans])
    return series


def window_values(svc_series, col, lo, hi):
    return [v for ts, v in zip(svc_series["ts"], svc_series[col]) if lo <= ts <= hi and v is not None]


def check_signatures(incidents, series, report):
    """Metrics must follow the pattern of the injected failure mode (and NORMAL must stay benign)."""
    problems = []
    for iid, meta in incidents.items():
        per = series.get(iid)
        t = meta.get("_t")
        if not per or not t:
            continue
        scenario, svc, root = meta["scenario"], meta["service"], meta.get("root_cause_service")
        ref = t["fault"] or t["start"]
        pre = (max(t["ws"], ref - timedelta(minutes=30)), ref - timedelta(minutes=1))
        inc = (t["start"], t["end"])

        def pre_med(s, col):
            vals = window_values(per[s], col, *pre)
            return statistics.median(vals) if vals else None

        def peak(s, col, lo=inc[0], hi=inc[1]):
            vals = window_values(per[s], col, lo, hi)
            return max(vals) if vals else None

        if scenario == NORMAL:
            for s, data in per.items():
                run = best = 0
                for v in data["error_rate"]:
                    run = run + 1 if v is not None and v > 5 else 0
                    best = max(best, run)
                if best >= 3:
                    problems.append(f"{iid}: NORMAL case has sustained error_rate > 5% on {s}")
                db = [v for v in data["db_connection_utilization"] if v is not None]
                if db and max(db) >= 90:
                    problems.append(f"{iid}: NORMAL case has saturated db utilization on {s}")
            continue

        if svc not in per:
            problems.append(f"{iid}: reported service {svc} has no metrics")
            continue
        err_up = peak(svc, "error_rate") - pre_med(svc, "error_rate")
        lat_ratio = peak(svc, "latency_ms") / pre_med(svc, "latency_ms")
        if err_up < 0.5 and lat_ratio < 1.5:
            problems.append(f"{iid}: reported service {svc} shows no error or latency increase")

        if scenario == "DB_CONNECTION_POOL_EXHAUSTION":
            if peak(root, "db_connection_utilization") < 90 or pre_med(root, "db_connection_utilization") > 75:
                problems.append(f"{iid}: {root} db_connection_utilization does not go from normal to saturated")
        elif scenario == "MEMORY_LEAK":
            base = pre_med(root, "memory_usage")
            leak = [(ts, v) for ts, v in zip(per[root]["ts"], per[root]["memory_usage"]) if t["fault"] <= ts <= t["end"]]
            top = max(v for _, v in leak)
            rise = top - base
            steps = [b - a for (_, a), (_, b) in zip(leak, leak[1:]) if b > a]
            if top < 80 or rise < 15:
                problems.append(f"{iid}: {root} memory does not grow substantially (base {base:.0f}%, max {top:.0f}%)")
            elif steps and max(steps) > 0.3 * rise:
                problems.append(f"{iid}: {root} memory growth is a spike rather than gradual")
        elif scenario == "DOWNSTREAM_SERVICE_TIMEOUT":
            ds_pre = pre_med(svc, "downstream_latency_ms")
            if ds_pre is None or peak(svc, "downstream_latency_ms") < 2.5 * ds_pre:
                problems.append(f"{iid}: {svc} downstream_latency_ms does not rise clearly")
            if peak(svc, "memory_usage") - pre_med(svc, "memory_usage") > 10:
                problems.append(f"{iid}: {svc} local memory changes too much for a downstream timeout")
    report.check("metric patterns match each scenario (and NORMAL cases stay benign)", problems)


def check_levels(incidents, log_stats, level_totals, report):
    report.check("INFO, WARN and ERROR logs all present", all(level_totals[lv] > 0 for lv in LEVELS),
                 ", ".join(f"{lv}={level_totals[lv]}" for lv in LEVELS))
    problems = []
    for iid, meta in incidents.items():
        s = log_stats.get(iid)
        if not s:
            continue
        lv = s["levels"]
        if lv["INFO"] == 0:
            problems.append(f"{iid}: no INFO (normal activity) logs")
        if meta["scenario"] != NORMAL:
            if lv["ERROR"] == 0 or lv["WARN"] == 0:
                problems.append(f"{iid}: failure incident without WARN or ERROR logs")
            if lv["INFO"] / max(1, s["n"]) < 0.4:
                problems.append(f"{iid}: logs dominated by failure records (INFO share < 40%)")
        elif lv["WARN"] == 0:
            problems.append(f"{iid}: NORMAL case has no occasional WARN logs")
    report.check("every case mixes normal activity with WARN/ERROR noise", problems)
    leaks = [f"{iid}: {s['leaks']} log messages mention the scenario label" for iid, s in log_stats.items() if s["leaks"]]
    report.check("ground-truth labels do not leak into log messages", leaks)


def cv(values):
    values = [v for v in values if v is not None]
    if len(values) < 2 or statistics.mean(values) == 0:
        return 0.0
    return statistics.pstdev(values) / statistics.mean(values)


def check_variation(incidents, series, log_stats, report):
    problems, details = [], []
    for scenario in FAILURE_SCENARIOS:
        ids = [i for i, m in incidents.items() if m["scenario"] == scenario]
        if len(ids) < 2:
            continue
        metas = [incidents[i] for i in ids]
        pairs = {(m["service"], m.get("root_cause_service")) for m in metas}
        severities = {m["severity"] for m in metas}
        durations = {m["duration_minutes"] if "duration_minutes" in m else (m["_t"]["end"] - m["_t"]["start"]) for m in metas}
        starts = {m["start_time"] for m in metas}
        peak_err, peak_lat, log_counts = [], [], []
        for i in ids:
            per, t, svc = series.get(i, {}), incidents[i]["_t"], incidents[i]["service"]
            if svc in per:
                peak_err.append(max(window_values(per[svc], "error_rate", t["start"], t["end"]) or [0]))
                peak_lat.append(max(window_values(per[svc], "latency_ms", t["start"], t["end"]) or [0]))
            log_counts.append(log_stats.get(i, {}).get("n", 0))
        signatures = [frozenset(log_stats[i]["templates"]["ERROR"]) for i in ids if i in log_stats]
        unique_sig = len(set(signatures)) / max(1, len(signatures))
        label = scenario.split("_")[0]
        if len(pairs) < 2:
            problems.append(f"{scenario}: all incidents affect the same service")
        if len(severities) < 2:
            problems.append(f"{scenario}: all incidents have severity {severities}")
        if len(durations) < 0.8 * len(ids):
            problems.append(f"{scenario}: incident durations barely vary")
        if len(starts) != len(ids):
            problems.append(f"{scenario}: duplicated start times")
        for name, values in (("peak error rate", peak_err), ("peak latency", peak_lat), ("log volume", log_counts)):
            if cv(values) < 0.1:
                problems.append(f"{scenario}: {name} nearly identical across incidents (cv={cv(values):.2f})")
        if unique_sig < 0.8:
            problems.append(f"{scenario}: error-message sets repeat across incidents ({unique_sig:.0%} unique)")
        details.append(f"{label}: {len(pairs)} service pairs, {len(severities)} severities, "
                       f"{unique_sig:.0%} unique error sets")
    report.check("failure incidents vary (services, severity, duration, magnitudes, messages)", problems,
                 "; ".join(details))


def check_keyword_shortcuts(incidents, log_stats, report):
    """No single WARN/ERROR template may appear in every incident of a scenario and in no other case."""
    problems, best = [], []
    presence = {}
    for iid, s in log_stats.items():
        for tpl in s["templates"]["ERROR"] | s["templates"]["WARN"]:
            presence.setdefault(tpl, set()).add(iid)
    for scenario in FAILURE_SCENARIOS:
        inside = {i for i, m in incidents.items() if m["scenario"] == scenario}
        outside = set(incidents) - inside
        top = (0.0, "")
        for tpl, ids in presence.items():
            recall = len(ids & inside) / max(1, len(inside))
            leak_out = len(ids & outside)
            if recall == 1.0 and leak_out == 0:
                problems.append(f"{scenario}: template {tpl[:90]!r} alone identifies every incident")
            if leak_out == 0 and recall > top[0]:
                top = (recall, tpl)
        best.append(f"{scenario.split('_')[0]} best exclusive template covers {top[0]:.0%}")
    report.check("root cause cannot be read from a single log template", problems, "; ".join(best))


def check_manifest(data_dir, report):
    path = data_dir / "generated" / "manifest.json"
    if not path.is_file():
        report.check("generated/manifest.json present", False, "missing")
        return
    manifest = json.loads(path.read_text(encoding="utf-8"))
    problems = []
    listed = manifest.get("files", {})
    for rel, digest in listed.items():
        target = data_dir / rel
        if not target.is_file():
            problems.append(f"{rel}: listed in manifest but missing")
        elif hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            problems.append(f"{rel}: checksum differs from manifest")
    for sub, pattern in (("raw/incidents", "*.json"), ("raw/logs", "*.jsonl"), ("raw/metrics", "*.csv")):
        for p in (data_dir / sub).glob(pattern):
            if p.relative_to(data_dir).as_posix() not in listed:
                problems.append(f"{p.relative_to(data_dir).as_posix()}: not listed in manifest")
    report.check("manifest checksums match the files on disk", problems,
                 f"{len(listed)} files, seed={manifest.get('seed')}")


def validate(data_dir, verbose=True):
    data_dir = Path(data_dir)
    report = Report()
    inc_dir, log_dir, met_dir = data_dir / "raw/incidents", data_dir / "raw/logs", data_dir / "raw/metrics"
    dirs_ok = report.check("dataset directories exist",
                           [f"missing {d}" for d in (inc_dir, log_dir, met_dir, data_dir / "generated") if not d.is_dir()])
    if dirs_ok:
        files = [p for d in (inc_dir, log_dir, met_dir, data_dir / "generated") for p in d.iterdir() if p.is_file()]
        report.check("no dataset file is empty", [f"{p.name} is empty" for p in files if p.stat().st_size == 0]
                     or ([] if files else ["no files found"]), f"{len(files)} files")
        incidents = load_incidents(inc_dir, report)
        check_counts_and_ground_truth(incidents, report)
        check_incident_times(incidents, report)
        log_stats, level_totals = check_logs(incidents, log_dir, report)
        series = check_metrics(incidents, met_dir, report)
        check_levels(incidents, log_stats, level_totals, report)
        check_signatures(incidents, series, report)
        check_variation(incidents, series, log_stats, report)
        check_keyword_shortcuts(incidents, log_stats, report)
        check_manifest(data_dir, report)
    if verbose:
        print(f"Dataset validation: {data_dir}")
        report.print()
        failed = sum(1 for _, ok, _, _ in report.results if not ok)
        total = len(report.results)
        print(f"Result: {'PASS' if report.ok else 'FAIL'} ({total - failed}/{total} checks passed)")
    return report.ok


def main(argv=None):
    parser = argparse.ArgumentParser(description="Validate the synthetic incident dataset.")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).resolve().parent.parent / "data",
                        help="dataset root (default: <repo>/data)")
    args = parser.parse_args(argv)
    return 0 if validate(args.data_dir.resolve()) else 1


if __name__ == "__main__":
    sys.exit(main())
