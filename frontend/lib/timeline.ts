import type { TimelineEvidence } from "@/lib/incidents";

export type TimelineCategory = "log" | "anomaly" | "window" | "change" | "boundary";

const changeTypes = new Set(["DEPLOYMENT_EVENT", "CHANGE_EVENT", "RESTART_EVENT"]);

export const categoryLabel: Record<TimelineCategory, string> = {
  log: "Log",
  anomaly: "Anomaly",
  window: "Anomaly window",
  change: "Change",
  boundary: "Incident boundary",
};

export function timelineCategory(item: Pick<TimelineEvidence, "source_type" | "evidence_type">): TimelineCategory {
  const type = item.evidence_type ?? "";
  if (type === "ANOMALY_WINDOW" || item.source_type === "ANOMALY_WINDOW") return "window";
  if (type === "ANOMALY" || item.source_type === "METRIC_ANOMALY") return "anomaly";
  if (changeTypes.has(type)) return "change";
  return "log";
}

export type TimelineRow =
  | { kind: "boundary"; id: string; timestamp: string; label: string }
  | { kind: "evidence"; item: TimelineEvidence };

export function timelineRows(start: string, end: string, items: TimelineEvidence[]): TimelineRow[] {
  const rows: TimelineRow[] = [
    { kind: "boundary", id: "alert-start", timestamp: start, label: "Alert start" },
    { kind: "boundary", id: "alert-end", timestamp: end, label: "Alert end" },
    ...items.map((item) => ({ kind: "evidence" as const, item })),
  ];
  const stamp = (row: TimelineRow) => (row.kind === "boundary" ? row.timestamp : row.item.timestamp);
  const rank = (row: TimelineRow) => (row.kind === "boundary" ? (row.id === "alert-start" ? 0 : 2) : 1);
  return rows.sort((left, right) => {
    const a = stamp(left);
    const b = stamp(right);
    if (a < b) return -1;
    if (a > b) return 1;
    return rank(left) - rank(right);
  });
}
