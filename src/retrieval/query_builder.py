"""Build an observational retrieval query from incident evidence.

The query uses incident context, anomaly windows, and the observational timeline.
It does not read evaluation fields (scenario, true root cause, fault timing, expected
symptoms, or the current incident's resolution).
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path

from correlation.models import IncidentTimeline
from detection.models import AnomalySeverity, IncidentAnomalyReport
from ingestion import DEFAULT_DATA_DIR, incident_path, load_incident_context
from ingestion.models import IncidentContext

from .models import RetrievalError

# Tokens that would copy the evaluation answer into the query. Matched on the finished text.
FORBIDDEN_QUERY = re.compile(
    r"DB_CONNECTION_POOL_EXHAUSTION|MEMORY_LEAK|DOWNSTREAM_SERVICE_TIMEOUT|"
    r"\btrue_root_cause\b|\bfault_start_time\b|\bexpected_symptoms\b|"
    r"\broot_cause_variant\b|\broot_cause_service\b|\broot_cause_detail\b|\bscenario\b",
    re.IGNORECASE,
)

METRIC_LANGUAGE = {
    "cpu_usage": "CPU usage",
    "memory_usage": "memory usage",
    "request_rate": "request rate",
    "latency_ms": "latency",
    "error_rate": "error rate",
    "db_connection_utilization": "database connection utilization",
    "downstream_latency_ms": "downstream latency",
}

# Log event types worth naming. Counts only; the query does not paste a root-cause label.
FOCUS_EVENTS = frozenset({
    "db_timeout", "db_connection_error", "db_connection_wait", "db_pool_stats",
    "slow_db_query", "db_error", "db_lock_wait", "db_statement_cancelled",
    "downstream_timeout", "downstream_error", "downstream_slow", "retry",
    "circuit_breaker_state_change", "operation_timeout", "health_check_failed",
    "gc_pause", "memory_pressure", "memory_allocation_failed", "oom_killed",
    "memory_stats", "request_failed", "slow_request", "application_error",
})
CHANGE_EVENTS = frozenset({
    "deployment_started", "deployment_completed", "config_change",
    "service_restart", "feature_flag_change", "autoscaling",
})


def build_query_for_incident(incident_id: str, data_dir: str | Path = DEFAULT_DATA_DIR) -> str:
    """Load observed artifacts for one current incident and describe them."""
    data_dir = Path(data_dir)
    context = load_incident_context(incident_path(incident_id, data_dir))
    anomalies = IncidentAnomalyReport.model_validate_json(
        (data_dir / "derived" / "anomalies" / f"{incident_id}.json").read_text(encoding="utf-8"))
    timeline = IncidentTimeline.model_validate_json(
        (data_dir / "derived" / "correlation" / f"{incident_id}.json").read_text(encoding="utf-8"))
    return build_retrieval_query(context, anomalies, timeline)


def build_retrieval_query(
    context: IncidentContext,
    anomaly_report: IncidentAnomalyReport,
    timeline: IncidentTimeline,
) -> str:
    """Describe what was observed. The text is the retrieval query, not a diagnosis."""
    if context.incident_id != anomaly_report.incident_id or context.incident_id != timeline.incident_id:
        raise RetrievalError("context, anomaly report, and timeline must be the same incident")
    sentences = [
        (f"{context.service} alert ({context.severity.value}, "
         f"about {context.duration_minutes:.0f} minutes): {context.title}."),
        _sentence(context.description),
        _metric_sentence(anomaly_report, context.service),
        _event_sentence(timeline, context.service),
        _change_sentence(timeline),
        _service_sentence(context.service, timeline.involved_services),
        _timing_sentence(context.start_time, timeline),
    ]
    text = " ".join(part for part in sentences if part)
    if FORBIDDEN_QUERY.search(text):
        raise RetrievalError(f"observational query for {context.incident_id} contains an evaluation label")
    return text


def _sentence(text: str) -> str:
    cleaned = " ".join(text.split())
    if not cleaned:
        return ""
    return cleaned if cleaned.endswith(".") else cleaned + "."


def _metric_sentence(report: IncidentAnomalyReport, alerting: str) -> str:
    """Summarize anomaly points per series, with the alerting service first."""
    by_series: dict[tuple[str, str], dict] = {}
    for point in report.points:
        slot = by_series.setdefault(
            (point.service, point.metric_name),
            {"count": 0, "severity": point.severity},
        )
        slot["count"] += 1
        if point.severity.rank > slot["severity"].rank:
            slot["severity"] = point.severity
    if not by_series:
        return "No metric anomaly points were observed."

    def sort_key(item: tuple[tuple[str, str], dict]) -> tuple:
        (service, _), slot = item
        return (service == alerting, slot["severity"].rank, slot["count"])

    ranked = sorted(by_series.items(), key=sort_key, reverse=True)
    chosen: list[tuple[tuple[str, str], dict]] = []
    off_service = 0
    for item in ranked:
        service = item[0][0]
        if service == alerting and sum(entry[0][0] == alerting for entry in chosen) < 3:
            chosen.append(item)
        elif service != alerting and off_service < 1 and item[1]["severity"].rank >= AnomalySeverity.MEDIUM.rank:
            chosen.append(item)
            off_service += 1
        if len(chosen) >= 4:
            break
    if not chosen:
        chosen = ranked[:3]
    clauses = []
    for (service, metric), slot in chosen:
        name = METRIC_LANGUAGE.get(metric, metric.replace("_", " "))
        if service == "database" and name.startswith("database "):
            name = name[len("database "):]
        clauses.append(
            f"{service} {name} was {_degree(slot['severity'])} ({slot['count']} anomalous points)"
        )
    alerting_slots = [slot for (service, _), slot in ranked if service == alerting]
    high_on_alert = any(slot["severity"] is AnomalySeverity.HIGH for slot in alerting_slots)
    body = "; ".join(clauses) + "."
    if not high_on_alert:
        return "Metric deviations on the alerting service were below high severity: " + body
    return "Metric anomaly points: " + body


def _degree(severity: AnomalySeverity) -> str:
    if severity is AnomalySeverity.HIGH:
        return "highly anomalous"
    if severity is AnomalySeverity.MEDIUM:
        return "anomalous"
    return "mildly elevated above baseline"


def _event_sentence(timeline: IncidentTimeline, alerting: str) -> str:
    counts: Counter[tuple[str, str]] = Counter()
    for item in timeline.evidence_items:
        if item.event_type is None or item.event_type.value not in FOCUS_EVENTS:
            continue
        counts[(item.service, item.event_type.value)] += item.occurrence_count
    if not counts:
        return ("No timeout, connection-wait, memory-pressure, or error events "
                "were retained on the observed timeline.")
    ranked = sorted(counts.items(), key=lambda item: (item[0][0] == alerting, item[1]), reverse=True)
    parts = []
    for (service, event_type), count in ranked[:6]:
        label = event_type.replace("_", " ")
        parts.append(f"{label} on {service} ({count})")
    return "Observed log events: " + "; ".join(parts) + "."


def _change_sentence(timeline: IncidentTimeline) -> str:
    seen: list[str] = []
    for item in timeline.evidence_items:
        if item.event_type is None or item.event_type.value not in CHANGE_EVENTS:
            continue
        label = f"{item.event_type.value.replace('_', ' ')} on {item.service}"
        if label not in seen:
            seen.append(label)
        if len(seen) >= 3:
            break
    if not seen:
        return ""
    return "Changes observed in the window: " + "; ".join(seen) + "."


def _service_sentence(alerting: str, involved: tuple[str, ...]) -> str:
    others = [service for service in involved if service != alerting]
    if not others:
        return f"Related observations stayed on {alerting}."
    return "Related services include " + ", ".join(others) + "."


def _timing_sentence(alert_start: datetime, timeline: IncidentTimeline) -> str:
    event = timeline.earliest_anomaly
    if event is None:
        return "No anomaly was placed on the timeline before or during the alert."
    delta_minutes = (event.timestamp - alert_start).total_seconds() / 60.0
    relation = "before" if delta_minutes < 0 else "after"
    title = " ".join(event.title.split())
    if len(title) > 160:
        title = title[:157] + "..."
    return (f"The earliest anomaly on the timeline is {abs(delta_minutes):.0f} minutes "
            f"{relation} the alert: {title}.")
