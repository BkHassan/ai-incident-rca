import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { IncidentDetailView } from "@/components/incidents/IncidentDetailView";
import type { IncidentDetail } from "@/lib/incidents";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const incident: IncidentDetail = {
  incident_id: "INC-011",
  title: "payment-api error-rate SLO burn",
  service: "payment-api",
  severity: "HIGH",
  start_time: "2026-02-03T06:18:15",
  end_time: "2026-02-03T06:41:59",
  duration_minutes: 23.7,
  description: "Elevated latency on payment-api with rising errors.",
  window_start: "2026-02-03T04:56:00",
  window_end: "2026-02-03T07:09:00",
  logs: {
    line_count: 4,
    by_level: { ERROR: 1 },
    services: ["payment-api"],
    event_types: [{ name: "request_failed", count: 1 }],
  },
  metrics: { row_count: 12, services: ["payment-api"], series: ["payment-api:error_rate"] },
  anomalies_available: true,
  anomaly_metrics: [
    {
      metric: "error_rate",
      label: "Error rate",
      point_count: 12,
      window_count: 1,
      peak_severity: "HIGH",
    },
  ],
  anomaly_windows: [
    {
      start_time: "2026-02-03T06:20:00",
      end_time: "2026-02-03T06:30:00",
      duration_minutes: 10,
      severity: "HIGH",
      anomaly_count: 12,
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
      timestamp: "2026-02-03T05:40:00",
      title: "deployment started on payment-api",
      summary: "deployment started on payment-api",
      service: "payment-api",
      source_type: "LOG",
      evidence_type: "DEPLOYMENT_EVENT",
      evidence_id: "LOG-000002",
      severity: "INFO",
      event_type: "DEPLOYMENT_STARTED",
      occurrence_count: 1,
    },
    {
      timestamp: "2026-02-03T06:19:00",
      title: "error_rate anomaly on payment-api",
      summary: "error_rate on payment-api was outside its baseline",
      service: "payment-api",
      source_type: "METRIC_ANOMALY",
      evidence_type: "ANOMALY",
      evidence_id: "ANOM-000091",
      severity: "HIGH",
      metric_name: "error_rate",
      occurrence_count: 1,
    },
    {
      timestamp: "2026-02-03T06:20:00",
      title: "request failed on payment-api",
      summary: "request failed on payment-api",
      service: "payment-api",
      source_type: "LOG",
      evidence_type: "ERROR_EVENT",
      evidence_id: "LOG-000010",
      severity: "ERROR",
      event_type: "REQUEST_FAILED",
      occurrence_count: 4,
      last_timestamp: "2026-02-03T06:24:00",
    },
    {
      timestamp: "2026-02-03T06:20:00",
      title: "anomaly window (error_rate) on payment-api",
      summary: "error_rate window on payment-api from 06:20 to 06:30",
      service: "payment-api",
      source_type: "ANOMALY_WINDOW",
      evidence_type: "ANOMALY_WINDOW",
      evidence_id: "ANOMWIN-000023",
      severity: "HIGH",
      metric_name: "error_rate",
      occurrence_count: 12,
      last_timestamp: "2026-02-03T06:30:00",
      related_evidence_ids: ["LOG-000010"],
    },
  ],
};

describe("evidence timeline", () => {
  it("shows only detected metrics, windows, and categorized records", () => {
    render(<IncidentDetailView incident={incident} />);
    expect(screen.getByRole("heading", { name: "Anomalies detected" })).toBeInTheDocument();
    expect(screen.getByText("Error rate")).toBeInTheDocument();
    expect(screen.queryByText("CPU")).not.toBeInTheDocument();
    expect(screen.queryByText("Memory")).not.toBeInTheDocument();
    expect(screen.getAllByText(/12 points/).length).toBeGreaterThan(0);
    expect(screen.getByText("Anomaly window")).toBeInTheDocument();
    expect(screen.getByText("Change")).toBeInTheDocument();
    expect(screen.getAllByText("Incident boundary").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("LOG-000002").closest("button")).toHaveTextContent("deployment started on payment-api");
  });

  it("opens the stored evidence record when a timeline item is clicked", () => {
    render(<IncidentDetailView incident={incident} />);
    fireEvent.click(screen.getByRole("button", { name: /ANOMWIN-000023/ }));
    const panel = screen.getByRole("complementary");
    expect(panel).toHaveTextContent("ANOMWIN-000023");
    expect(panel).toHaveTextContent("error_rate window on payment-api from 06:20 to 06:30");
    expect(panel).toHaveTextContent("error_rate");
    fireEvent.click(screen.getByRole("button", { name: "LOG-000010" }));
    expect(panel).toHaveTextContent("LOG-000010");
    expect(panel).toHaveTextContent("request failed on payment-api");
    expect(panel).toHaveTextContent("REQUEST_FAILED");
  });
});
