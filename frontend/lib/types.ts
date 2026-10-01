/** Mirrors src/investigation/models.py. Do not add evaluation fields. */

export const INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE";

export type EvidenceSource =
  | "LOG"
  | "METRIC_ANOMALY"
  | "ANOMALY_WINDOW"
  | "HISTORICAL_INCIDENT"
  | "TECHNICAL_DOCUMENT";

export interface RootCauseHypothesis {
  cause: string;
  /** Uncalibrated ranking score in [0, 1]. Not a probability. */
  confidence: number;
  supporting_evidence_ids: string[];
  contradicting_evidence_ids: string[];
  rationale: string;
}

export interface EvidenceReference {
  evidence_id: string;
  source_type: EvidenceSource;
  short_description: string;
}

export interface RecommendedAction {
  action: string;
  rationale: string;
  evidence_ids: string[];
}

export interface SimilarIncident {
  incident_id: string;
  similarity_note: string;
}

export interface TimelineEntry {
  evidence_id: string;
  timestamp: string;
  description: string;
}

export interface RCAResult {
  incident_id: string;
  summary: string;
  root_cause: RootCauseHypothesis;
  confidence: number;
  alternative_causes: RootCauseHypothesis[];
  supporting_evidence: EvidenceReference[];
  contradicting_evidence: EvidenceReference[];
  timeline: TimelineEntry[];
  recommended_actions: RecommendedAction[];
  similar_incidents: SimilarIncident[];
}

export type TimelineKind = "observation" | "anomaly" | "error" | "investigation";

export interface IncidentHeaderModel {
  incident_id: string;
  title: string;
  severity: string;
  services: string[];
  status: string;
  start_time: string;
}

export interface TimelineEventModel {
  evidence_id: string;
  timestamp: string;
  description: string;
  kind: TimelineKind;
  service: string;
  /** False for the review marker, which is not an observed fault. */
  observed: boolean;
}

export interface MetricSeriesModel {
  id: string;
  label: string;
  unit: string;
  points: number[];
  baseline: number;
  anomalyFrom: number | null;
  anomalyTo: number | null;
  summary: string;
}

export interface EvidenceCardModel {
  evidence_id: string;
  source_type: EvidenceSource;
  timestamp: string;
  service: string;
  description: string;
  why_it_matters: string;
  role: "supporting" | "contradicting";
}

export interface HistoricalCardModel {
  incident_id: string;
  similarity_note: string;
  incident_type: string;
  symptoms: string;
  resolution_summary: string;
}

export interface TechnicalCardModel {
  document_id: string;
  title: string;
  section: string;
  excerpt: string;
  source_path: string;
}

/** Demo-only display fields. The live API returns RCAResult, not this object. */
export interface FixturePresentation {
  header: Omit<IncidentHeaderModel, "incident_id">;
  timelineMeta: Record<string, { kind: TimelineKind; service: string }>;
  metrics: MetricSeriesModel[];
  evidenceMeta: Record<string, { timestamp: string; service: string; why_it_matters: string }>;
  historicalMeta: Record<string, Omit<HistoricalCardModel, "incident_id" | "similarity_note">>;
  technicalMeta: Record<string, { title: string; section: string; excerpt: string; source_path: string }>;
}

export interface InvestigationView {
  source: "fixture" | "live";
  header: IncidentHeaderModel;
  rca: RCAResult;
  timeline: TimelineEventModel[];
  metrics: MetricSeriesModel[];
  evidence: EvidenceCardModel[];
  historical: HistoricalCardModel[];
  technical: TechnicalCardModel[];
}
