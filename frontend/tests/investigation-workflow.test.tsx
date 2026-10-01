import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvestigationWorkspace } from "@/components/investigation/InvestigationWorkspace";
import { INSUFFICIENT_EVIDENCE, type RCAResult } from "@/lib/types";

const result: RCAResult = {
  incident_id: "INC-011",
  summary: "Callers waited on payment-api.",
  root_cause: {
    cause: "requests queued in payment-api",
    confidence: 0.62,
    supporting_evidence_ids: ["LOG-000010"],
    contradicting_evidence_ids: [],
    rationale: "Error logs cite timeouts on the alerting service.",
  },
  confidence: 0.62,
  alternative_causes: [],
  supporting_evidence: [
    {
      evidence_id: "LOG-000010",
      source_type: "LOG",
      short_description: "payment-api returned 500",
    },
  ],
  contradicting_evidence: [],
  timeline: [
    {
      evidence_id: "LOG-000010",
      timestamp: "2026-02-03T06:20:00",
      description: "payment-api returned 500",
    },
  ],
  recommended_actions: [
    {
      action: "Compare pool usage with the error log.",
      rationale: "The cited log is the observation.",
      evidence_ids: ["LOG-000010"],
    },
  ],
  similar_incidents: [{ incident_id: "HIST-007", similarity_note: "Earlier timeout notes." }],
};

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

describe("investigation workflow", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends one POST and renders the RCA result", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, result));
    vi.stubGlobal("fetch", fetchMock);
    render(<InvestigationWorkspace incidentId="INC-011" autostart={false} />);
    expect(screen.getByText(/has not been sent/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Investigate incident" }));
    expect((await screen.findAllByText("Callers waited on payment-api.")).length).toBeGreaterThan(0);
    expect(screen.getAllByText("requests queued in payment-api").length).toBeGreaterThan(0);
    expect(screen.getByText(/not a probability/i)).toBeInTheDocument();
    expect(screen.getByText(/not the cause of this incident/i)).toBeInTheDocument();
    const posts = fetchMock.mock.calls.filter((call) => (call[1] as RequestInit | undefined)?.method === "POST");
    expect(posts).toHaveLength(1);
    const [url, init] = posts[0] as [string, RequestInit];
    expect(url).toContain("/api/incidents/investigate");
    expect(init.method).toBe("POST");
    expect(init.body).toBe(JSON.stringify({ incident_id: "INC-011" }));
    expect(screen.queryByText(/stage complete|checkmark/i)).not.toBeInTheDocument();
  });

  it("renders insufficient evidence without a failure type", async () => {
    const insufficient: RCAResult = {
      ...result,
      root_cause: {
        cause: INSUFFICIENT_EVIDENCE,
        confidence: 0.2,
        supporting_evidence_ids: [],
        contradicting_evidence_ids: [],
        rationale: "The cited records do not identify a mechanism.",
      },
      confidence: 0.2,
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, insufficient)));
    render(<InvestigationWorkspace incidentId="INC-011" autostart />);
    expect(await screen.findByRole("heading", { name: "Insufficient evidence" })).toBeInTheDocument();
    expect(screen.queryByText(INSUFFICIENT_EVIDENCE)).not.toBeInTheDocument();
  });

  it.each([
    [404, { error: "not_found", detail: "No incident INC-099" }, "Incident not found"],
    [422, { detail: [{ msg: "pattern" }] }, "Id rejected"],
    [502, { error: "investigation_failed", detail: "the model request failed" }, "Investigation failed"],
    [503, { error: "vector_store_missing", detail: "Chroma store not found." }, "Service not ready"],
  ])("shows status %s", async (status, body, title) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(status, body)));
    render(<InvestigationWorkspace incidentId="INC-011" autostart />);
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.queryByText("requests queued in payment-api")).not.toBeInTheDocument();
  });

  it("shows a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<InvestigationWorkspace incidentId="INC-011" autostart />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be reached");
  });

  it("rejects a malformed result", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse(200, { incident_id: "INC-011" })));
    render(<InvestigationWorkspace incidentId="INC-011" autostart />);
    expect(await screen.findByText("Response was not an RCA result")).toBeInTheDocument();
  });
});
