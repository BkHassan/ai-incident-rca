import type { FixturePresentation, MetricSeriesModel, RCAResult } from "@/lib/types";

function series(
  id: string,
  label: string,
  unit: string,
  baseline: number,
  points: number[],
  anomalyFrom: number | null,
  anomalyTo: number | null,
  summary: string,
): MetricSeriesModel {
  return { id, label, unit, baseline, points, anomalyFrom, anomalyTo, summary };
}

const poolPresentation: FixturePresentation = {
  header: {
    title: "payment-api error-rate SLO burn",
    severity: "HIGH",
    services: ["payment-api"],
    status: "Alert window ended",
    start_time: "2026-02-03T06:18:15",
  },
  timelineMeta: {
    "ANOMWIN-000023": { kind: "anomaly", service: "payment-api" },
    "ANOM-000044": { kind: "anomaly", service: "payment-api" },
    "ANOM-000091": { kind: "error", service: "payment-api" },
    "LOG-000812": { kind: "error", service: "payment-api" },
  },
  metrics: [
    series(
      "db_connection_utilization",
      "DB connection utilization",
      "%",
      38,
      [36, 37, 38, 40, 48, 63, 79, 90, 96, 98, 98, 97],
      4,
      11,
      "Illustrative series: utilization leaves a mid-30s baseline and climbs toward the cap before errors accumulate.",
    ),
    series(
      "latency_ms",
      "Latency",
      "ms",
      190,
      [180, 188, 195, 210, 280, 520, 1400, 4200, 9000, 12000, 13100, 13200],
      4,
      11,
      "Illustrative series: latency stays near baseline, then rises with the utilization climb.",
    ),
    series(
      "error_rate",
      "Error rate",
      "%",
      0.4,
      [0.2, 0.2, 0.3, 0.4, 0.6, 1.2, 3, 8, 14, 20, 23, 24],
      6,
      11,
      "Illustrative series: the error rate moves later than utilization and latency.",
    ),
    series(
      "memory_usage",
      "Memory usage",
      "%",
      62,
      [61, 62, 61, 62, 63, 62, 61, 62, 63, 62, 61, 62],
      null,
      null,
      "Illustrative series: memory stays near baseline and does not climb with the errors.",
    ),
  ],
  evidenceMeta: {
    "ANOMWIN-000023": {
      timestamp: "2026-02-03T06:06:00",
      service: "payment-api",
      why_it_matters:
        "The pool window starts before the error-rate alert. That order is consistent with waits building up, and it does not by itself prove the cause.",
    },
    "LOG-000812": {
      timestamp: "2026-02-03T06:21:40",
      service: "payment-api",
      why_it_matters:
        "Acquire-timeout wording means the request failed while borrowing a connection, before a query was sent.",
    },
    "ANOM-000091": {
      timestamp: "2026-02-03T06:18:15",
      service: "payment-api",
      why_it_matters: "This is the error-rate movement that opened the alert. It is a symptom, not a cause.",
    },
    "ANOM-000044": {
      timestamp: "2026-02-03T06:12:00",
      service: "payment-api",
      why_it_matters:
        "Latency rises ahead of the error rate. Callers can look slow for more than one reason, so this also fits a downstream-timeout hypothesis.",
    },
    "ANOM-000012": {
      timestamp: "2026-02-03T06:18:15",
      service: "payment-api",
      why_it_matters: "Memory staying near baseline cuts against a memory-growth explanation for the same window.",
    },
    database_003: {
      timestamp: "",
      service: "knowledge",
      why_it_matters:
        "Background note on how a full pool shows up. It is not a measurement from this incident.",
    },
  },
  historicalMeta: {
    "HIST-007": {
      incident_type: "Historical connection-wait incident",
      symptoms: "Connection waits and elevated latency on a service that borrows database connections.",
      resolution_summary:
        "The past record describes a pool-related mitigation. That outcome is not a finding for this incident.",
    },
    "HIST-012": {
      incident_type: "Historical acquire-timeout incident",
      symptoms: "Borrow timeouts after pool utilization held near its cap.",
      resolution_summary:
        "Historical reference only. Similarity of symptoms is not identity of cause.",
    },
  },
  technicalMeta: {
    database_003: {
      title: "Database connections, pools, and slow queries",
      section: "Acquisition timeouts",
      excerpt:
        "When a borrow exceeds the pool acquire timeout, the request fails before a query is sent. Latency rises first because work sits in the wait queue, and the error rate peaks later. A full pool together with acquire timeouts points at pool capacity or connections that were not released. A statement timeout is a different failure: it happens after a connection was borrowed.",
      source_path: "knowledge/docs/database.md",
    },
  },
};

const quietPresentation: FixturePresentation = {
  header: {
    title: "inventory-service: traffic anomaly alert auto-resolved",
    severity: "LOW",
    services: ["inventory-service"],
    status: "Alert window ended",
    start_time: "2026-02-10T09:43:32",
  },
  timelineMeta: {},
  metrics: [],
  evidenceMeta: {},
  historicalMeta: {},
  technicalMeta: {},
};

export const fixturePresentations: Record<string, FixturePresentation> = {
  "INC-011": poolPresentation,
  "INC-014": quietPresentation,
};

function hypothesis(
  cause: string,
  confidence: number,
  supporting: string[],
  contradicting: string[],
  rationale: string,
) {
  return {
    cause,
    confidence,
    supporting_evidence_ids: supporting,
    contradicting_evidence_ids: contradicting,
    rationale,
  };
}

const inc011: RCAResult = {
  incident_id: "INC-011",
  summary:
    "Connection utilization on payment-api rises before latency and the error rate. Acquire-timeout logs appear while memory stays near its baseline. That pattern is more consistent with pool exhaustion than with a memory climb or a downstream timeout.",
  root_cause: hypothesis(
    "Database connection pool exhaustion",
    0.72,
    ["ANOMWIN-000023", "LOG-000812", "ANOM-000091", "database_003"],
    ["ANOM-000012"],
    "The pool window leads the alert, and the cited errors are acquire timeouts rather than a named dependency failure. The technical note describes that mechanism. It is background, not a measurement from this incident.",
  ),
  confidence: 0.72,
  alternative_causes: [
    hypothesis(
      "Slow query or lock wait",
      0.34,
      ["ANOMWIN-000023"],
      [],
      "A statement that holds connections can fill a pool. No lock-wait or slow-query log was cited, so this remains possible and weaker than the acquire-timeout reading.",
    ),
    hypothesis(
      "Downstream service timeout",
      0.22,
      ["ANOM-000044"],
      ["LOG-000812"],
      "Latency did rise, which can happen when a dependency stalls. The cited failure text is an acquire timeout on the local pool, which cuts against a pure downstream timeout.",
    ),
    hypothesis(
      "Memory pressure",
      0.08,
      ["ANOM-000091"],
      ["ANOM-000012"],
      "Errors rose, but the memory series stays near baseline. That contradicts a memory-growth account of this window.",
    ),
  ],
  supporting_evidence: [
    {
      evidence_id: "ANOMWIN-000023",
      source_type: "ANOMALY_WINDOW",
      short_description: "payment-api database connection utilization climbed from the mid-30s toward the cap.",
    },
    {
      evidence_id: "LOG-000812",
      source_type: "LOG",
      short_description: "payment-api logged timeouts while acquiring a database connection.",
    },
    {
      evidence_id: "ANOM-000091",
      source_type: "METRIC_ANOMALY",
      short_description: "payment-api error rate rose after utilization and latency had already moved.",
    },
    {
      evidence_id: "database_003",
      source_type: "TECHNICAL_DOCUMENT",
      short_description: "Note on acquire timeouts versus statement timeouts.",
    },
    {
      evidence_id: "ANOM-000044",
      source_type: "METRIC_ANOMALY",
      short_description: "payment-api latency rose ahead of the error-rate alert.",
    },
  ],
  contradicting_evidence: [
    {
      evidence_id: "ANOM-000012",
      source_type: "METRIC_ANOMALY",
      short_description: "payment-api memory stayed near baseline through the alert window.",
    },
    {
      evidence_id: "LOG-000812",
      source_type: "LOG",
      short_description: "The same acquire-timeout log cuts against a downstream-timeout reading.",
    },
  ],
  timeline: [
    {
      evidence_id: "ANOMWIN-000023",
      timestamp: "2026-02-03T06:06:00",
      description: "Connection utilization left its baseline and kept climbing.",
    },
    {
      evidence_id: "ANOM-000044",
      timestamp: "2026-02-03T06:12:00",
      description: "Latency increased while the pool window was already open.",
    },
    {
      evidence_id: "ANOM-000091",
      timestamp: "2026-02-03T06:18:15",
      description: "Error-rate alert opened on payment-api.",
    },
    {
      evidence_id: "LOG-000812",
      timestamp: "2026-02-03T06:21:40",
      description: "Acquire-timeout errors were logged on payment-api.",
    },
  ],
  recommended_actions: [
    {
      action: "Compare pool utilization with request rate across the same minutes.",
      rationale: "A climb without a matching traffic increase is more informative than utilization alone.",
      evidence_ids: ["ANOMWIN-000023"],
    },
    {
      action: "Read the acquire-timeout logs and check whether a query was sent.",
      rationale: "An acquire timeout fails before the statement. A statement timeout fails after a borrow.",
      evidence_ids: ["LOG-000812"],
    },
    {
      action: "Check memory and CPU beside the error-rate movement.",
      rationale: "Memory near baseline makes a leak a poor fit for this window.",
      evidence_ids: ["ANOM-000012", "ANOM-000091"],
    },
    {
      action: "Use the pool note as a checklist, not as a conclusion.",
      rationale: "The document explains the mechanism. It does not observe this incident.",
      evidence_ids: ["database_003"],
    },
  ],
  similar_incidents: [
    {
      incident_id: "HIST-007",
      similarity_note:
        "Shared observations: connection waits and latency. The past cause is not copied onto this incident.",
    },
    {
      incident_id: "HIST-012",
      similarity_note:
        "Shared observations: borrow timeouts after utilization held high. Similarity is not identity of cause.",
    },
  ],
};

const inc014: RCAResult = {
  incident_id: "INC-014",
  summary:
    "The alert describes a brief traffic movement on inventory-service and no customer reports. No pool, memory, or downstream-failure evidence was cited, so a failure mode is not supported.",
  root_cause: hypothesis(
    "INSUFFICIENT_EVIDENCE",
    0,
    [],
    [],
    "Latency in the alert text stays small, and this demo supplies no error, pool, or memory evidence to name a cause.",
  ),
  confidence: 0,
  alternative_causes: [],
  supporting_evidence: [],
  contradicting_evidence: [],
  timeline: [],
  recommended_actions: [
    {
      action: "Collect error, pool, and dependency evidence before naming a cause.",
      rationale: "The current observations do not distinguish a fault from a short traffic movement.",
      evidence_ids: [],
    },
  ],
  similar_incidents: [],
};

export const fixtureResults: Record<string, RCAResult> = {
  "INC-011": inc011,
  "INC-014": inc014,
};

export function fixtureResult(incidentId: string): RCAResult | undefined {
  return fixtureResults[incidentId];
}

export function fixturePresentation(incidentId: string): FixturePresentation | undefined {
  return fixturePresentations[incidentId];
}
