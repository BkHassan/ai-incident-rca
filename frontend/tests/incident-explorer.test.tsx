import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { IncidentExplorer } from "@/components/incidents/IncidentExplorer";
import { IncidentDetail } from "@/components/incidents/IncidentDetail";
import { IncidentDetailView } from "@/components/incidents/IncidentDetailView";
import { IncidentList } from "@/components/incidents/IncidentList";
import type { IncidentDetail as IncidentRecord, IncidentSummary } from "@/lib/incidents";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const incidents: IncidentSummary[] = [
  {
    incident_id: "INC-011",
    title: "payment-api error-rate SLO burn",
    service: "payment-api",
    severity: "HIGH",
    start_time: "2026-02-03T06:18:15",
    end_time: "2026-02-03T06:41:59",
    duration_minutes: 23.7,
    description: "Elevated latency on payment-api with rising errors.",
  },
  {
    incident_id: "INC-014",
    title: "quiet period",
    service: "orders-api",
    severity: "LOW",
    start_time: "2026-02-04T01:00:00",
    end_time: "2026-02-04T01:10:00",
    duration_minutes: 10,
    description: "No customer-facing errors were reported.",
  },
];

const detail: IncidentRecord = {
  ...incidents[0],
  window_start: "2026-02-03T04:56:00",
  window_end: "2026-02-03T07:09:00",
  logs: {
    line_count: 4,
    by_level: { ERROR: 1, WARN: 1 },
    services: ["payment-api"],
    event_types: [{ name: "request_failed", count: 1 }],
  },
  metrics: { row_count: 12, services: ["payment-api"], series: ["payment-api:error_rate"] },
  anomalies_available: true,
  anomaly_windows: [
    {
      start_time: "2026-02-03T06:20:00",
      end_time: "2026-02-03T06:30:00",
      duration_minutes: 10,
      severity: "MEDIUM",
      anomaly_count: 3,
      services: ["payment-api"],
      metrics: ["error_rate"],
      peak_z_score: 4.2,
      peak_metric: "error_rate",
      peak_service: "payment-api",
    },
  ],
  timeline_available: true,
  observed_services: ["payment-api"],
  timeline: [
    {
      timestamp: "2026-02-03T06:20:00",
      title: "request failed on payment-api",
      service: "payment-api",
      source_type: "LOG",
      evidence_id: "LOG-000010",
      severity: "ERROR",
    },
  ],
};

describe("incident explorer", () => {
  it("filters the catalog by service and search text", () => {
    render(<IncidentList incidents={incidents} />);
    expect(screen.getByRole("link", { name: /INC-011/ })).toHaveAttribute("href", "/incidents/INC-011");
    expect(screen.getByRole("link", { name: /INC-014/ })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Alerting service"), { target: { value: "orders-api" } });
    expect(screen.queryByRole("link", { name: /INC-011/ })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Alerting service"), { target: { value: "" } });
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "quiet" } });
    expect(screen.getByRole("link", { name: /INC-014/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /INC-011/ })).not.toBeInTheDocument();
  });

  it("shows an empty filter state", () => {
    render(<IncidentList incidents={incidents} />);
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "no-such-incident" } });
    expect(screen.getByText("No incidents match")).toBeInTheDocument();
  });

  it("keeps ground truth out of the detail view", () => {
    render(<IncidentDetailView incident={detail} />);
    expect(screen.getByRole("link", { name: "Investigate incident" })).toHaveAttribute(
      "href",
      "/investigations?incident=INC-011&run=1",
    );
    expect(screen.getByText("Observed logs")).toBeInTheDocument();
    expect(screen.getByText("Anomalies detected")).toBeInTheDocument();
    expect(screen.getByText(/Order is not causation/)).toBeInTheDocument();
    expect(screen.queryByText(/true root cause|resolution|scenario|DB_CONNECTION_POOL/i)).not.toBeInTheDocument();
  });

  it("shows an unknown id without calling the catalog", async () => {
    render(<IncidentDetail incidentId="not-an-id" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("INC-011");
    expect(screen.queryByText("payment-api error-rate SLO burn")).not.toBeInTheDocument();
  });

  it("shows a catalog error when the service cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));
    render(<IncidentExplorer />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be reached");
    vi.unstubAllGlobals();
  });

  it("shows a missing incident from a 404", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: "not_found", detail: "No incident INC-099." }),
      }),
    );
    render(<IncidentDetail incidentId="INC-099" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("No incident INC-099.");
    vi.unstubAllGlobals();
  });
});
