export type HistoricalHit = {
  rank: number;
  incident_id: string;
  score: number;
  text: string;
  service?: string | null;
  occurred_at?: string | null;
  severity?: string | null;
  duration_minutes?: number | null;
  historical_root_cause?: string | null;
  historical_root_cause_service?: string | null;
};

export type TechnicalHit = {
  rank: number;
  document_id: string;
  title: string;
  section: string;
  score: number;
  text: string;
  document_name?: string | null;
};

export type RetrievalPayload = {
  incident_id: string;
  query: string;
  historical_incidents: HistoricalHit[];
  technical_documents: TechnicalHit[];
};

export type RetrievalOrigin = "retrieval" | "fixture";

export function previewText(text: string, limit = 280): string {
  const flat = text.replace(/\s+/g, " ").trim();
  if (flat.length <= limit) return flat;
  return `${flat.slice(0, limit).trimEnd()}…`;
}
