import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RcaWorkspace } from "@/components/investigation/RcaWorkspace";
import { fixtureResult } from "@/data/investigation-fixture";
import { reviewSummary } from "@/lib/review";
import { INSUFFICIENT_EVIDENCE, type RCAResult } from "@/lib/types";

const success = fixtureResult("INC-011");
const insufficient = fixtureResult("INC-014");

function result(overrides: Partial<RCAResult> = {}): RCAResult {
  return { ...success, ...overrides };
}

describe("RCA workspace", () => {
  it("shows why a successful result reached its hypothesis", () => {
    render(<RcaWorkspace result={success} />);
    expect(screen.getByRole("heading", { level: 1, name: "INC-011" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Database connection pool exhaustion" })).toBeInTheDocument();
    expect(screen.getAllByText(success.summary).length).toBeGreaterThan(0);
    expect(screen.getByText("0.72")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Why this conclusion" })).toBeInTheDocument();
    expect(screen.getAllByText("ANOMWIN-000023").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Source Anomaly window/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/2026-02-03 06:06:00/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/Supports the hypothesis/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "Contradicting evidence" })).toBeInTheDocument();
    expect(screen.getAllByText(/Contradicts the hypothesis/).length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "HIST-007" })).toBeInTheDocument();
    expect(screen.getByText(success.similar_incidents[0].similarity_note)).toBeInTheDocument();
    expect(screen.getAllByText("Model hypothesis").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Observed fact").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Recommended action").length).toBeGreaterThan(0);
    expect(screen.queryByText(/true_root_cause|resolution summary|why it matters/i)).not.toBeInTheDocument();
  });

  it("renders insufficient evidence without a failure type", () => {
    render(<RcaWorkspace result={insufficient} />);
    expect(screen.getByTestId("insufficient")).toHaveTextContent("Insufficient evidence");
    expect(screen.queryByText(INSUFFICIENT_EVIDENCE)).not.toBeInTheDocument();
    expect(screen.getByText("No supporting evidence was returned.")).toBeInTheDocument();
    expect(screen.getByText("No alternative causes were returned.")).toBeInTheDocument();
  });

  it("shows empty alternative and contradicting sections", () => {
    render(
      <RcaWorkspace
        result={result({
          alternative_causes: [],
          contradicting_evidence: [],
          root_cause: { ...success.root_cause, contradicting_evidence_ids: [] },
        })}
      />,
    );
    expect(screen.getByText("No alternative causes were returned.")).toBeInTheDocument();
    expect(screen.getByText("No contradicting evidence was returned.")).toBeInTheDocument();
    expect(screen.getAllByText(success.supporting_evidence[0].short_description).length).toBeGreaterThan(0);
  });

  it("renders every item in a long evidence list and a long hypothesis", () => {
    const longCause = `Pool exhaustion ${"detail ".repeat(80)}`;
    const items = Array.from({ length: 24 }, (_, index) => ({
      evidence_id: `LOG-${String(index + 1).padStart(6, "0")}`,
      source_type: "LOG" as const,
      short_description: `Observed log ${index + 1}`,
    }));
    render(
      <RcaWorkspace
        result={result({
          summary: longCause,
          root_cause: { ...success.root_cause, cause: longCause, rationale: longCause },
          supporting_evidence: items,
          timeline: [],
        })}
      />,
    );
    expect(screen.getByRole("heading", { name: /Pool exhaustion detail/ })).toHaveTextContent(longCause.trim());
    expect(screen.getByText("LOG-000001")).toBeInTheDocument();
    expect(screen.getByText("LOG-000024")).toBeInTheDocument();
    expect(screen.getByText("Observed log 24")).toBeInTheDocument();
    expect(screen.queryByText(/UTC/)).not.toBeInTheDocument();
  });

  it("builds the review sheet and actions only from the returned result", () => {
    render(<RcaWorkspace result={success} />);
    const review = reviewSummary(success);
    const sheet = screen.getByTestId("operational-summary");
    expect(screen.getByLabelText("Investigation output")).toHaveTextContent("Investigation");
    expect(screen.getByLabelText("Investigation output")).toHaveTextContent("Findings");
    expect(screen.getByLabelText("Investigation output")).toHaveTextContent("Evidence");
    expect(screen.getByLabelText("Investigation output")).toHaveTextContent("Actions");
    expect(sheet).toHaveTextContent(review.rootCause);
    expect(sheet).toHaveTextContent(String(review.supportingCount));
    expect(sheet).toHaveTextContent(String(review.contradictingCount));
    expect(sheet).toHaveTextContent(String(review.historicalCount));
    expect(sheet).toHaveTextContent(String(review.technicalCount));
    expect(sheet).toHaveTextContent(String(review.actionCount));
    expect(sheet).toHaveTextContent(review.alternatives[0]);
    expect(screen.getByRole("heading", { name: success.recommended_actions[0].action })).toBeInTheDocument();
    expect(screen.getAllByText(success.supporting_evidence[0].short_description).length).toBeGreaterThan(1);
    expect(screen.queryByRole("button", { name: /fix|remediat|slack|jira|pagerduty/i })).not.toBeInTheDocument();
    expect(screen.queryByText(/priority/i)).not.toBeInTheDocument();
  });
});
