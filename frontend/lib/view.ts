import type { FixturePresentation } from "@/lib/types";
import { INSUFFICIENT_EVIDENCE } from "@/lib/types";
import type {
  EvidenceCardModel,
  HistoricalCardModel,
  InvestigationView,
  RCAResult,
  TechnicalCardModel,
  TimelineEventModel,
} from "@/lib/types";

export function isInsufficient(rca: RCAResult): boolean {
  return rca.root_cause.cause === INSUFFICIENT_EVIDENCE;
}

export function buildInvestigationView(
  rca: RCAResult,
  source: "fixture" | "live",
  presentation?: FixturePresentation,
): InvestigationView {
  const header = presentation
    ? { incident_id: rca.incident_id, ...presentation.header }
    : {
        incident_id: rca.incident_id,
        title: rca.incident_id,
        severity: "UNKNOWN",
        services: [],
        status: "Result received",
        start_time: rca.timeline[0]?.timestamp ?? "",
      };

  const timeline: TimelineEventModel[] = rca.timeline.map((entry) => {
    const meta = presentation?.timelineMeta[entry.evidence_id];
    return {
      evidence_id: entry.evidence_id,
      timestamp: entry.timestamp,
      description: entry.description,
      kind: meta?.kind ?? "observation",
      service: meta?.service ?? "",
      observed: true,
    };
  });
  if (source === "fixture" && rca.timeline.length > 0) {
    timeline.push({
      evidence_id: "",
      timestamp: "",
      description: "Review assembled from the evidence above. This marker is not an observed fault.",
      kind: "investigation",
      service: "",
      observed: false,
    });
  }

  const cited = new Map<string, EvidenceCardModel>();
  for (const ref of rca.supporting_evidence) {
    cited.set(ref.evidence_id, cardFromReference(ref, "supporting", presentation));
  }
  for (const ref of rca.contradicting_evidence) {
    if (!cited.has(ref.evidence_id)) {
      cited.set(ref.evidence_id, cardFromReference(ref, "contradicting", presentation));
    }
  }

  const historical: HistoricalCardModel[] = rca.similar_incidents.map((item) => {
    const meta = presentation?.historicalMeta[item.incident_id];
    return {
      incident_id: item.incident_id,
      similarity_note: item.similarity_note,
      incident_type: meta?.incident_type ?? "Historical incident",
      symptoms: meta?.symptoms ?? "",
      resolution_summary: meta?.resolution_summary ?? "",
    };
  });

  const technical: TechnicalCardModel[] = [];
  const seenDocs = new Set<string>();
  for (const ref of [...rca.supporting_evidence, ...rca.contradicting_evidence]) {
    if (ref.source_type !== "TECHNICAL_DOCUMENT" || seenDocs.has(ref.evidence_id)) {
      continue;
    }
    seenDocs.add(ref.evidence_id);
    const meta = presentation?.technicalMeta[ref.evidence_id];
    technical.push({
      document_id: ref.evidence_id,
      title: meta?.title ?? ref.short_description,
      section: meta?.section ?? "",
      excerpt: meta?.excerpt ?? ref.short_description,
      source_path: meta?.source_path ?? "",
    });
  }

  return {
    source,
    header,
    rca,
    timeline,
    metrics: presentation?.metrics ?? [],
    evidence: [...cited.values()],
    historical,
    technical,
  };
}

function cardFromReference(
  ref: RCAResult["supporting_evidence"][number],
  role: "supporting" | "contradicting",
  presentation?: FixturePresentation,
): EvidenceCardModel {
  const meta = presentation?.evidenceMeta[ref.evidence_id];
  return {
    evidence_id: ref.evidence_id,
    source_type: ref.source_type,
    timestamp: meta?.timestamp ?? "",
    service: meta?.service ?? "",
    description: ref.short_description,
    why_it_matters: meta?.why_it_matters ?? ref.short_description,
    role,
  };
}
