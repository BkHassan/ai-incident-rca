"""Check that an RCA cites only evidence that was supplied."""

from __future__ import annotations

from .models import (
    INSUFFICIENT_EVIDENCE,
    CitedEvidence,
    EvidenceReference,
    InvalidRCA,
    InvestigationContext,
    RCAResult,
    RecommendedAction,
    RootCauseHypothesis,
    TimelineEntry,
)


def validate_rca(result: RCAResult, context: InvestigationContext) -> RCAResult:
    """Reject an RCA that cites unknown ids or disagrees with the incident it was given.

    Descriptions and timestamps on references are replaced with the supplied evidence
    text so the result cannot introduce a fact that was not in the context.
    """
    if result.incident_id != context.incident_id:
        raise InvalidRCA(
            f"result incident_id {result.incident_id} does not match {context.incident_id}"
        )
    known = context.allowed_ids()
    _require_known(_hypothesis_ids(result.root_cause), known, "root_cause")
    for index, alternative in enumerate(result.alternative_causes):
        _require_known(_hypothesis_ids(alternative), known, f"alternative_causes[{index}]")
        if (result.root_cause.cause != INSUFFICIENT_EVIDENCE
                and alternative.cause != INSUFFICIENT_EVIDENCE
                and not alternative.supporting_evidence_ids):
            raise InvalidRCA(f"alternative_causes[{index}] needs supporting evidence ids")
    for action in result.recommended_actions:
        _require_known(action.evidence_ids, known, "recommended_actions")
        if result.root_cause.cause != INSUFFICIENT_EVIDENCE and not action.evidence_ids:
            raise InvalidRCA("recommended actions need evidence ids")

    historical_ids = {
        item.evidence_id for item in context.evidence
        if item.source_type.value == "HISTORICAL_INCIDENT"
    }
    for similar in result.similar_incidents:
        if similar.incident_id not in historical_ids:
            raise InvalidRCA(
                f"similar incident {similar.incident_id} was not in the retrieval results"
            )

    cited_support = _unique(
        result.root_cause.supporting_evidence_ids
        + [eid for alt in result.alternative_causes for eid in alt.supporting_evidence_ids]
    )
    cited_against = _unique(
        result.root_cause.contradicting_evidence_ids
        + [eid for alt in result.alternative_causes for eid in alt.contradicting_evidence_ids]
    )
    # References the model listed must also be known. Unknown ids are rejected, not kept.
    _require_known([ref.evidence_id for ref in result.supporting_evidence], known, "supporting_evidence")
    _require_known([ref.evidence_id for ref in result.contradicting_evidence], known, "contradicting_evidence")
    _require_known([entry.evidence_id for entry in result.timeline], known, "timeline")

    return result.model_copy(update={
        "supporting_evidence": [_reference(eid, known) for eid in cited_support],
        "contradicting_evidence": [_reference(eid, known) for eid in cited_against],
        "timeline": [_timeline_entry(entry.evidence_id, known) for entry in result.timeline],
        "recommended_actions": [
            RecommendedAction(
                action=action.action,
                rationale=action.rationale,
                evidence_ids=list(action.evidence_ids),
            )
            for action in result.recommended_actions
        ],
        "similar_incidents": list(result.similar_incidents),
    })


def insufficient_result(incident_id: str, reason: str) -> RCAResult:
    """A valid RCA used when there is nothing to cite."""
    hypothesis = RootCauseHypothesis(
        cause=INSUFFICIENT_EVIDENCE,
        confidence=0.0,
        supporting_evidence_ids=[],
        contradicting_evidence_ids=[],
        rationale=reason,
    )
    return RCAResult(
        incident_id=incident_id,
        summary=reason,
        root_cause=hypothesis,
        confidence=0.0,
        alternative_causes=[],
        supporting_evidence=[],
        contradicting_evidence=[],
        timeline=[],
        recommended_actions=[RecommendedAction(
            action="Collect more logs and metrics before naming a cause.",
            rationale=reason,
            evidence_ids=[],
        )],
        similar_incidents=[],
    )


def _hypothesis_ids(hypothesis: RootCauseHypothesis) -> list[str]:
    return list(hypothesis.supporting_evidence_ids) + list(hypothesis.contradicting_evidence_ids)


def _require_known(ids: list[str], known: dict[str, CitedEvidence], where: str) -> None:
    unknown = [eid for eid in ids if eid not in known]
    if unknown:
        raise InvalidRCA(f"{where} cites evidence ids that were not supplied: {unknown}")


def _unique(ids: list[str]) -> list[str]:
    seen: list[str] = []
    for eid in ids:
        if eid not in seen:
            seen.append(eid)
    return seen


def _reference(evidence_id: str, known: dict[str, CitedEvidence]) -> EvidenceReference:
    item = known[evidence_id]
    return EvidenceReference(
        evidence_id=item.evidence_id,
        source_type=item.source_type,
        short_description=item.short_description,
    )


def _timeline_entry(evidence_id: str, known: dict[str, CitedEvidence]) -> TimelineEntry:
    item = known[evidence_id]
    return TimelineEntry(
        evidence_id=item.evidence_id,
        timestamp=item.timestamp,
        description=item.short_description,
    )
