import type { RetrievalPayload } from "@/lib/retrieval";

/** Isolated development records. Production retrieval does not import this module. */

export function fixtureRetrieval(incidentId: string): RetrievalPayload | null {
  if (incidentId !== "INC-011") return null;
  return {
    incident_id: "INC-011",
    query: "payment-api alert: elevated latency and errors. Fixture query, not a live retrieval query.",
    historical_incidents: [
      {
        rank: 1,
        incident_id: "HIST-001",
        score: 0.81,
        service: "payment-api",
        occurred_at: "2025-07-04T03:00:36",
        severity: "LOW",
        duration_minutes: 35,
        historical_root_cause: "DOWNSTREAM_SERVICE_TIMEOUT",
        historical_root_cause_service: "payment-api",
        text: [
          "Incident HIST-001",
          "Title: payment-api error-rate SLO burn; upstream acquirer-gateway slow",
          "Symptoms:",
          "- outbound calls to a dependency approaching the client timeout",
          "- callers receiving 502/503/504 responses",
        ].join("\n"),
      },
    ],
    technical_documents: [
      {
        rank: 1,
        document_id: "database_003",
        title: "Database connections, pools, and slow queries",
        section: "Saturation and maximum connections",
        score: 0.74,
        document_name: "database.md",
        text: "Document: Database connections, pools, and slow queries\nSection: Saturation and maximum connections\n\nSaturation means checked-out connections sit at the configured maximum and new work queues.",
      },
    ],
  };
}
