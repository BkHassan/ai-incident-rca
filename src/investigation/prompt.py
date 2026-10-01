"""Render the investigation prompt from an InvestigationContext.

The prompt contains only supplied evidence. It does not contain evaluation labels.
"""

from __future__ import annotations

from .models import EvidenceSource, InvestigationContext

_RULES = """
You are investigating a software incident. Use ONLY the evidence in this prompt.

Rank plausible root-cause hypotheses. For every hypothesis explain the reasoning, cite supporting evidence ids, and cite contradicting evidence ids when the supplied evidence cuts against that hypothesis. Do not invent evidence ids, metrics, logs, or timestamps. Distinguish what was observed from what you conclude. An earlier event is not proof that it produced a later one.

Rules:
1. Do not assume the first anomaly is the root cause.
2. Do not assume a deployment or other change caused the incident merely because it occurred earlier.
3. Do not use severity as proof of a root cause.
4. Do not use incident duration as proof of a root cause.
5. Do not invent missing telemetry. If a series or log type is absent from the evidence, do not claim it.
6. If the evidence is insufficient to support a cause, set the primary cause to INSUFFICIENT_EVIDENCE, use a low confidence, and say what is missing.
7. Keep alternative hypotheses when more than one cause remains plausible.
8. Every root-cause claim must cite evidence ids from the allowed list. Never create an id.

Historical incidents and technical notes are background. A past incident being similar does not mean this incident has the same cause. Compare observations. Do not copy a past outcome onto this case.

confidence is an uncalibrated score from 0 to 1 for ranking only. It is not a probability.
""".strip()


def render_prompt(context: InvestigationContext) -> str:
    groups = {source: [] for source in EvidenceSource}
    for item in context.evidence:
        groups[item.source_type].append(item)
    lines = [
        _RULES,
        "",
        "Incident under investigation",
        f"incident_id: {context.incident_id}",
        f"alerting_service: {context.service}",
        f"severity: {context.severity}",
        f"title: {context.title}",
        f"description: {context.description}",
        f"alert_start: {context.alert_start}",
        f"alert_end: {context.alert_end}",
        f"duration_minutes: {context.duration_minutes:.1f}",
        "involved_services: " + ", ".join(context.involved_services),
        "",
        "Allowed evidence ids (cite only these):",
    ]
    for item in context.evidence:
        lines.append(f"- {item.evidence_id} [{item.source_type.value}] {item.short_description}")
    lines.append("")
    lines.append("Anomaly windows and metric anomalies:")
    lines.extend(_section(groups[EvidenceSource.ANOMALY_WINDOW] + groups[EvidenceSource.METRIC_ANOMALY]))
    lines.append("")
    lines.append("Log evidence:")
    lines.extend(_section(groups[EvidenceSource.LOG]))
    lines.append("")
    lines.append("Similar historical incidents (background only; not the cause of this incident):")
    lines.extend(_section(groups[EvidenceSource.HISTORICAL_INCIDENT]) or ["- none retrieved"])
    lines.append("")
    lines.append("Technical notes:")
    lines.extend(_section(groups[EvidenceSource.TECHNICAL_DOCUMENT]) or ["- none retrieved"])
    lines.append("")
    lines.append("Retrieval query that selected the historical incidents and technical notes:")
    lines.append(context.retrieval_query or "(empty)")
    lines.append("")
    lines.append(
        "Return the primary hypothesis, up to two alternatives, the evidence references, "
        "a short timeline using allowed ids, recommended next checks, and any historical "
        "incidents that were actually similar. If you cite a historical id, the note must "
        "describe shared observations, not transfer that past case's outcome."
    )
    return "\n".join(lines)


def _section(items) -> list[str]:
    rows = []
    for item in items:
        stamp = f"{item.timestamp} " if item.timestamp else ""
        rows.append(f"- {item.evidence_id} {stamp}{item.detail}")
    return rows
