import { INSUFFICIENT_EVIDENCE, type RCAResult } from "@/lib/types";

/** Counts and labels taken only from an RCAResult. */
export function reviewSummary(result: RCAResult) {
  const cited = [...result.supporting_evidence, ...result.contradicting_evidence];
  return {
    rootCause: result.root_cause.cause === INSUFFICIENT_EVIDENCE ? "Insufficient evidence" : result.root_cause.cause,
    summary: result.summary,
    supportingCount: result.supporting_evidence.length,
    contradictingCount: result.contradicting_evidence.length,
    alternatives: result.alternative_causes.map((item) => item.cause),
    historicalCount: result.similar_incidents.length,
    technicalCount: cited.filter((item) => item.source_type === "TECHNICAL_DOCUMENT").length,
    actionCount: result.recommended_actions.length,
  };
}
