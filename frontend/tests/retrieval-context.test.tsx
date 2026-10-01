import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RetrievalContext } from "@/components/investigation/RetrievalContext";
import { retrievalSource } from "@/lib/api/retrieval";
import type { RetrievalPayload } from "@/lib/retrieval";

const payload: RetrievalPayload = {
  incident_id: "INC-011",
  query: "payment-api latency and error rate",
  historical_incidents: [
    {
      rank: 1,
      incident_id: "HIST-001",
      score: 0.81,
      service: "payment-api",
      occurred_at: "2025-07-04T03:00:36",
      severity: "LOW",
      historical_root_cause: "DOWNSTREAM_SERVICE_TIMEOUT",
      historical_root_cause_service: "acquirer-gateway",
      text: `${"symptom ".repeat(50)}TAIL_MARKER_991`,
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
      text: "Saturation means checked-out connections sit at the configured maximum.",
    },
  ],
};

describe("retrieval context", () => {
  it("shows retrieved historical and technical records without calling them the current cause", () => {
    render(<RetrievalContext incidentId="INC-011" origin="retrieval" payload={payload} error={null} />);
    expect(screen.getByText("Current incident")).toBeInTheDocument();
    expect(screen.getByText("Retrieval")).toBeInTheDocument();
    expect(screen.getByText("Historical / technical context")).toBeInTheDocument();
    expect(screen.getByText("Investigation")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Similar historical incidents" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "HIST-001" })).toBeInTheDocument();
    expect(screen.getByText(/cosine similarity 0.81/)).toBeInTheDocument();
    expect(screen.getByText(/DOWNSTREAM_SERVICE_TIMEOUT/)).toBeInTheDocument();
    expect(screen.getAllByText(/not the cause of the current incident/i).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Technical knowledge" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Database connections, pools, and slow queries" })).toBeInTheDocument();
    expect(screen.getByText(/Saturation and maximum connections/)).toBeInTheDocument();
    expect(screen.getByText("database_003")).toBeInTheDocument();
    expect(screen.queryByText(/Fixture \/ dev data/)).not.toBeInTheDocument();
    expect(screen.queryByText(/TAIL_MARKER_991/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Show retrieved text" }));
    expect(screen.getByText(/TAIL_MARKER_991/)).toBeInTheDocument();
  });

  it("labels an explicit fixture and does not use that path by default", () => {
    render(<RetrievalContext incidentId="INC-011" origin="fixture" payload={payload} error={null} />);
    expect(screen.getByRole("status")).toHaveTextContent("Fixture / dev data");
    expect(retrievalSource()).toBe("retrieval");
  });
});
