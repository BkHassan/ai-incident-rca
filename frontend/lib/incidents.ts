/** Incident catalog types. Field names match the read-only API, which uses incident context only. */

export type IncidentSummary = {
  incident_id: string;
  title: string;
  service: string;
  severity: string;
  start_time: string;
  end_time: string;
  duration_minutes: number;
  description: string;
};

export type NamedCount = {
  name: string;
  count: number;
};

export type IncidentDetail = IncidentSummary & {
  window_start: string;
  window_end: string;
  logs: {
    line_count: number;
    by_level: Record<string, number>;
    services: string[];
    event_types: NamedCount[];
  };
  metrics: {
    row_count: number;
    services: string[];
    series: string[];
  };
  anomalies_available: boolean;
  anomaly_windows: AnomalyWindow[];
  anomaly_metrics?: AnomalyMetricSummary[];
  timeline_available: boolean;
  observed_services: string[];
  timeline: TimelineEvidence[];
};

export type AnomalyWindow = {
  start_time: string;
  end_time: string;
  duration_minutes: number;
  severity: string;
  anomaly_count: number;
  services: string[];
  metrics: string[];
  peak_z_score: number | null;
  peak_metric: string;
  peak_service: string;
};

export type AnomalyMetricSummary = {
  metric: string;
  label: string;
  point_count: number;
  window_count: number;
  peak_severity: string | null;
};

export type TimelineEvidence = {
  timestamp: string;
  title: string;
  summary?: string;
  service: string;
  source_type: string;
  evidence_type?: string;
  evidence_id: string;
  severity: string | null;
  metric_name?: string | null;
  event_type?: string | null;
  occurrence_count?: number;
  last_timestamp?: string | null;
  related_evidence_ids?: string[];
};

export const severityOrder = ["CRITICAL", "HIGH", "MEDIUM", "LOW"] as const;

const groundTruthKeys = [
  "scenario",
  "true_root_cause",
  "root_cause_service",
  "root_cause_variant",
  "root_cause_detail",
  "fault_start_time",
  "expected_symptoms",
  "affected_services",
  "resolution",
];

export function formatTimestamp(value: string): string {
  if (!value.trim()) return "—";
  const normalized = value.replace("T", " ").replace(/\.\d+/, "").replace(/Z$/, "").trim();
  const shown = normalized.length > 19 ? normalized.slice(0, 19) : normalized;
  return `${shown} UTC`;
}

export function formatDuration(minutes: number): string {
  const rounded = Math.round(minutes * 10) / 10;
  return `${rounded} min`;
}

export function filterIncidents(
  incidents: IncidentSummary[],
  query: string,
  service: string,
  severity: string,
): IncidentSummary[] {
  const needle = query.trim().toLowerCase();
  return incidents.filter((incident) => {
    if (service && incident.service !== service) return false;
    if (severity && incident.severity !== severity) return false;
    if (!needle) return true;
    const haystack = [incident.incident_id, incident.title, incident.service, incident.description]
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  });
}

export function uniqueSorted(values: string[]): string[] {
  return [...new Set(values)].sort((a, b) => a.localeCompare(b));
}

export function severitiesIn(incidents: IncidentSummary[]): string[] {
  const present = new Set(incidents.map((incident) => incident.severity));
  const known = severityOrder.filter((severity) => present.has(severity));
  const extra = uniqueSorted([...present].filter((severity) => !severityOrder.includes(severity as (typeof severityOrder)[number])));
  return [...known, ...extra];
}

export function responseHasGroundTruth(value: unknown): boolean {
  if (Array.isArray(value)) return value.some(responseHasGroundTruth);
  if (!value || typeof value !== "object") return false;
  return Object.entries(value).some(
    ([key, nested]) => groundTruthKeys.includes(key) || responseHasGroundTruth(nested),
  );
}
