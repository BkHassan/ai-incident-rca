import type { EvidenceSource } from "@/lib/types";

const SOURCE_LABEL: Record<EvidenceSource, string> = {
  LOG: "Log",
  METRIC_ANOMALY: "Anomaly",
  ANOMALY_WINDOW: "Anomaly window",
  HISTORICAL_INCIDENT: "Historical",
  TECHNICAL_DOCUMENT: "Technical",
};

export function evidenceSourceLabel(source: EvidenceSource): string {
  return SOURCE_LABEL[source];
}

export function formatTimestamp(value: string): string {
  if (!value.trim()) return "—";
  const normalized = value.replace("T", " ").replace(/\.\d+/, "").replace(/Z$/, "").trim();
  const shown = normalized.length > 19 ? normalized.slice(0, 19) : normalized;
  return `${shown} UTC`;
}

export function formatScore(value: number): string {
  return value.toFixed(2);
}
