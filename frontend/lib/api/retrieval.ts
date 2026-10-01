import type { HistoricalHit, RetrievalOrigin, RetrievalPayload, TechnicalHit } from "@/lib/retrieval";

const SECRET = /(?:AIza|AQ\.)[\w\-]+/g;

export class RetrievalClientError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 0, code = "retrieval_failed") {
    super(message);
    this.name = "RetrievalClientError";
    this.status = status;
    this.code = code;
  }
}

/** Live retrieval unless NEXT_PUBLIC_RETRIEVAL_SOURCE=fixture. The default never reads the fixture. */
export function retrievalSource(): RetrievalOrigin {
  return process.env.NEXT_PUBLIC_RETRIEVAL_SOURCE === "fixture" ? "fixture" : "retrieval";
}

export async function loadRetrieval(incidentId: string): Promise<{ origin: RetrievalOrigin; payload: RetrievalPayload }> {
  if (retrievalSource() === "fixture") {
    const { fixtureRetrieval } = await import("@/data/retrieval-fixture");
    const payload = fixtureRetrieval(incidentId);
    if (!payload) {
      throw new RetrievalClientError(`No retrieval fixture for ${incidentId}.`, 0, "fixture_missing");
    }
    return { origin: "fixture", payload };
  }
  return { origin: "retrieval", payload: await fetchRetrieval(incidentId) };
}

export async function fetchRetrieval(incidentId: string): Promise<RetrievalPayload> {
  const base = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  let response: Response;
  try {
    response = await fetch(`${base}/api/incidents/${incidentId}/retrieval`);
  } catch {
    throw new RetrievalClientError("The retrieval service could not be reached.");
  }
  if (!response.ok) {
    let detail = "Retrieval could not be completed.";
    let code = "retrieval_failed";
    try {
      const body = (await response.json()) as { detail?: unknown; error?: unknown };
      if (typeof body.detail === "string" && body.detail.trim()) detail = body.detail;
      if (typeof body.error === "string" && body.error.trim()) code = body.error;
    } catch {
      detail = "Retrieval could not be completed.";
    }
    throw new RetrievalClientError(detail.replace(SECRET, "[redacted]").slice(0, 300), response.status, code);
  }
  return parseRetrieval(await response.json());
}

export function parseRetrieval(value: unknown): RetrievalPayload {
  if (!value || typeof value !== "object") throw malformed();
  const body = value as Record<string, unknown>;
  if (typeof body.incident_id !== "string" || typeof body.query !== "string") throw malformed();
  if (!Array.isArray(body.historical_incidents) || !Array.isArray(body.technical_documents)) throw malformed();
  return {
    incident_id: body.incident_id,
    query: body.query,
    historical_incidents: body.historical_incidents.map(readHistorical),
    technical_documents: body.technical_documents.map(readTechnical),
  };
}

function readHistorical(value: unknown): HistoricalHit {
  if (!value || typeof value !== "object") throw malformed();
  const item = value as Record<string, unknown>;
  if (typeof item.incident_id !== "string" || typeof item.text !== "string" || typeof item.score !== "number") {
    throw malformed();
  }
  return {
    rank: typeof item.rank === "number" ? item.rank : 0,
    incident_id: item.incident_id,
    score: item.score,
    text: item.text,
    service: optionalText(item.service),
    occurred_at: optionalText(item.occurred_at),
    severity: optionalText(item.severity),
    duration_minutes: typeof item.duration_minutes === "number" ? item.duration_minutes : null,
    historical_root_cause: optionalText(item.historical_root_cause),
    historical_root_cause_service: optionalText(item.historical_root_cause_service),
  };
}

function readTechnical(value: unknown): TechnicalHit {
  if (!value || typeof value !== "object") throw malformed();
  const item = value as Record<string, unknown>;
  if (
    typeof item.document_id !== "string" ||
    typeof item.title !== "string" ||
    typeof item.section !== "string" ||
    typeof item.text !== "string" ||
    typeof item.score !== "number"
  ) {
    throw malformed();
  }
  return {
    rank: typeof item.rank === "number" ? item.rank : 0,
    document_id: item.document_id,
    title: item.title,
    section: item.section,
    score: item.score,
    text: item.text,
    document_name: optionalText(item.document_name),
  };
}

function optionalText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function malformed(): RetrievalClientError {
  return new RetrievalClientError("Response was not a retrieval result.", 200, "malformed");
}
