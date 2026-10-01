import { fixturePresentation, fixtureResult } from "@/data/investigation-fixture";
import type { RCAResult } from "@/lib/types";
import { buildInvestigationView } from "@/lib/view";
import type { InvestigationView } from "@/lib/types";

const SECRET = /(?:AIza|AQ\.)[\w\-]+/g;

export class InvestigationClientError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "InvestigationClientError";
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

/** Synchronous fixture view for tests and the demo page. */
export function loadFixtureView(incidentId: string): InvestigationView {
  const rca = fixtureResult(incidentId);
  if (!rca) {
    throw new InvestigationClientError(`No demo fixture for ${incidentId}.`);
  }
  return buildInvestigationView(rca, "fixture", fixturePresentation(incidentId));
}
