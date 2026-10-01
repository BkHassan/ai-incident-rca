import type { IncidentDetail, IncidentSummary } from "@/lib/incidents";

export class IncidentClientError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "IncidentClientError";
    this.status = status;
  }
}

function apiBase(): string {
  return (process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");
}

async function readJson(path: string): Promise<unknown> {
  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`);
  } catch {
    throw new IncidentClientError("The incident service could not be reached.");
  }
  if (!response.ok) {
    let detail = "The incident service could not be reached.";
    try {
      const body = (await response.json()) as { detail?: unknown };
      if (typeof body.detail === "string" && body.detail.trim()) {
        detail = body.detail;
      } else if (response.status === 422) {
        detail = "Use an incident id like INC-011.";
      }
    } catch {
      if (response.status === 422) detail = "Use an incident id like INC-011.";
    }
    throw new IncidentClientError(detail, response.status);
  }
  return response.json();
}

export async function fetchIncidents(): Promise<IncidentSummary[]> {
  const body = (await readJson("/api/incidents")) as { incidents?: IncidentSummary[] };
  if (!Array.isArray(body.incidents)) {
    throw new IncidentClientError("The incident catalog response was not a list.");
  }
  return body.incidents;
}

export async function fetchIncident(incidentId: string): Promise<IncidentDetail> {
  return (await readJson(`/api/incidents/${incidentId}`)) as IncidentDetail;
}
