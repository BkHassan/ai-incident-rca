import { fixturePresentation, fixtureResult } from "@/data/investigation-fixture";
import type { RCAResult } from "@/lib/types";
import { buildInvestigationView } from "@/lib/view";
import type { InvestigationView } from "@/lib/types";

const SECRET = /(?:AIza|AQ\.)[\w\-]+/g;

export class InvestigationClientError extends Error {
  status: number;
  code: string;

  constructor(message: string, status = 0, code = "investigation_failed") {
    super(message);
    this.name = "InvestigationClientError";
    this.status = status;
    this.code = code;
  }
}

export type InvestigationSource = "fixture" | "live";

/** Fixture unless NEXT_PUBLIC_INVESTIGATION_SOURCE=live. The browser never calls Gemini. */
export function investigationSource(): InvestigationSource {
  return process.env.NEXT_PUBLIC_INVESTIGATION_SOURCE === "live" ? "live" : "fixture";
}

export function publicErrorMessage(error: unknown): string {
  const raw = error instanceof Error ? error.message : "The investigation service could not be reached.";
  const cleaned = raw.replace(SECRET, "[redacted]");
  if (/api[_ ]?key/i.test(cleaned)) {
    return "The investigation service could not be reached.";
  }
  return cleaned.slice(0, 300) || "The investigation service could not be reached.";
}

export async function investigateIncident(incidentId: string): Promise<RCAResult> {
  if (investigationSource() === "fixture") {
    const result = fixtureResult(incidentId);
    if (!result) {
      throw new InvestigationClientError(`No demo fixture for ${incidentId}.`);
    }
    return result;
  }

  const base = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
  let response: Response;
  try {
    response = await fetch(`${base}/api/incidents/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ incident_id: incidentId }),
    });
  } catch {
    throw new InvestigationClientError("The investigation service could not be reached.");
  }

  if (!response.ok) {
    let detail = "The investigation service could not be reached.";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail.trim()) {
        detail = body.detail;
      }
    } catch {
      detail = "The investigation service could not be reached.";
    }
    throw new InvestigationClientError(publicErrorMessage(new Error(detail)));
  }

  return (await response.json()) as RCAResult;
}

export async function loadInvestigationView(incidentId: string): Promise<InvestigationView> {
  const source = investigationSource();
  const rca = await investigateIncident(incidentId);
  const presentation = source === "fixture" ? fixturePresentation(incidentId) : undefined;
  return buildInvestigationView(rca, source, presentation);
}

const inflight = new Map<string, Promise<RCAResult>>();

function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function malformed(): InvestigationClientError {
  return new InvestigationClientError(
    "The response was not an RCA result.",
    200,
    "malformed_response",
  );
}

function readHypothesis(value: unknown): RCAResult["root_cause"] {
  if (!isRecord(value) || typeof value.cause !== "string" || !value.cause || typeof value.confidence !== "number") {
    throw malformed();
  }
  if (typeof value.rationale !== "string" || !value.rationale) throw malformed();
  return {
    cause: value.cause,
    confidence: value.confidence,
    supporting_evidence_ids: readIds(value.supporting_evidence_ids),
    contradicting_evidence_ids: readIds(value.contradicting_evidence_ids),
    rationale: value.rationale,
  };
}

function readIds(value: unknown): string[] {
  if (!Array.isArray(value) || value.some((item) => typeof item !== "string" || !item)) throw malformed();
  return value;
}

const sources = new Set(["LOG", "METRIC_ANOMALY", "ANOMALY_WINDOW", "HISTORICAL_INCIDENT", "TECHNICAL_DOCUMENT"]);

export function parseRcaResult(value: unknown): RCAResult {
  if (!isRecord(value) || typeof value.incident_id !== "string" || !value.incident_id) throw malformed();
  if (typeof value.summary !== "string" || !value.summary) throw malformed();
  const root = readHypothesis(value.root_cause);
  if (typeof value.confidence !== "number" || Math.abs(value.confidence - root.confidence) > 1e-6) throw malformed();
  if (!Array.isArray(value.alternative_causes)) throw malformed();
  if (!Array.isArray(value.supporting_evidence) || !Array.isArray(value.contradicting_evidence)) throw malformed();
  if (!Array.isArray(value.timeline) || !Array.isArray(value.recommended_actions)) throw malformed();
  if (!Array.isArray(value.similar_incidents)) throw malformed();
  return {
    incident_id: value.incident_id,
    summary: value.summary,
    root_cause: root,
    confidence: value.confidence,
    alternative_causes: value.alternative_causes.map(readHypothesis),
    supporting_evidence: value.supporting_evidence.map(readEvidence),
    contradicting_evidence: value.contradicting_evidence.map(readEvidence),
    timeline: value.timeline.map(readTimeline),
    recommended_actions: value.recommended_actions.map(readAction),
    similar_incidents: value.similar_incidents.map(readSimilar),
  };
}

function readEvidence(value: unknown): RCAResult["supporting_evidence"][number] {
  if (!isRecord(value) || typeof value.evidence_id !== "string" || typeof value.short_description !== "string") {
    throw malformed();
  }
  if (typeof value.source_type !== "string" || !sources.has(value.source_type)) throw malformed();
  return {
    evidence_id: value.evidence_id,
    source_type: value.source_type as RCAResult["supporting_evidence"][number]["source_type"],
    short_description: value.short_description,
  };
}

function readTimeline(value: unknown): RCAResult["timeline"][number] {
  if (!isRecord(value) || typeof value.evidence_id !== "string" || typeof value.description !== "string") {
    throw malformed();
  }
  return {
    evidence_id: value.evidence_id,
    timestamp: typeof value.timestamp === "string" ? value.timestamp : "",
    description: value.description,
  };
}

function readAction(value: unknown): RCAResult["recommended_actions"][number] {
  if (!isRecord(value) || typeof value.action !== "string" || typeof value.rationale !== "string") throw malformed();
  return { action: value.action, rationale: value.rationale, evidence_ids: readIds(value.evidence_ids) };
}

function readSimilar(value: unknown): RCAResult["similar_incidents"][number] {
  if (!isRecord(value) || typeof value.incident_id !== "string" || typeof value.similarity_note !== "string") {
    throw malformed();
  }
  return { incident_id: value.incident_id, similarity_note: value.similarity_note };
}

function errorFromResponse(status: number, body: unknown): InvestigationClientError {
  const record = isRecord(body) ? body : {};
  const code = typeof record.error === "string" ? record.error : "";
  const detail = typeof record.detail === "string" ? publicErrorMessage(new Error(record.detail)) : "";
  if (status === 404) {
    return new InvestigationClientError(detail || "No incident with that id.", 404, code || "not_found");
  }
  if (status === 422) {
    return new InvestigationClientError("Use an incident id like INC-011.", 422, "validation_error");
  }
  if (status === 503) {
    return new InvestigationClientError(detail || "The investigation service is not ready.", 503, code || "configuration_error");
  }
  if (status === 502) {
    return new InvestigationClientError(detail || "The investigation failed.", 502, code || "investigation_failed");
  }
  return new InvestigationClientError(detail || "The investigation service could not be reached.", status, code || "investigation_failed");
}

/** Always calls POST /api/incidents/investigate. Does not use demo fixtures. */
export function runInvestigation(incidentId: string): Promise<RCAResult> {
  const existing = inflight.get(incidentId);
  if (existing) return existing;
  const request = postInvestigation(incidentId).finally(() => {
    if (inflight.get(incidentId) === request) inflight.delete(incidentId);
  });
  inflight.set(incidentId, request);
  return request;
}

async function postInvestigation(incidentId: string): Promise<RCAResult> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}/api/incidents/investigate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ incident_id: incidentId }),
    });
  } catch {
    throw new InvestigationClientError("The investigation service could not be reached.", 0, "network");
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }
  if (!response.ok) throw errorFromResponse(response.status, body);
  return parseRcaResult(body);
}

/** Synchronous fixture view for tests and the demo page. */
export function loadFixtureView(incidentId: string): InvestigationView {
  const rca = fixtureResult(incidentId);
  if (!rca) {
    throw new InvestigationClientError(`No demo fixture for ${incidentId}.`);
  }
  return buildInvestigationView(rca, "fixture", fixturePresentation(incidentId));
}
