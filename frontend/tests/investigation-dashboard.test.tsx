import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { InvestigationScreen } from "@/components/investigation/InvestigationScreen";
import { fixtureResult } from "@/data/investigation-fixture";
import { loadFixtureView } from "@/lib/api/investigation";

const view = loadFixtureView("INC-011");
const quiet = loadFixtureView("INC-014");

describe("investigation dashboard", () => {
  it("renders the investigation page from the fixture", () => {
    render(<InvestigationScreen mode="result" view={view} />);
    expect(screen.getByRole("heading", { level: 1, name: /INC-011/ })).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/not a live Gemini/i);
    expect(fixtureResult("INC-011")).not.toHaveProperty("true_root_cause");
    expect(fixtureResult("INC-011")).not.toHaveProperty("scenario");
  });

  it("renders the root cause hypothesis without calling it a probability", () => {
    render(<InvestigationScreen mode="result" view={view} />);
    expect(screen.getByRole("heading", { name: "Database connection pool exhaustion" })).toBeInTheDocument();
    expect(screen.getByText("0.72")).toBeInTheDocument();
    expect(screen.getAllByText(/Not a probability/i).length).toBeGreaterThan(0);
    expect(screen.queryByText(/probability of/i)).not.toBeInTheDocument();
  });

  it("renders key evidence and links a supporting id to that card", () => {
    render(<InvestigationScreen mode="result" view={view} />);
    expect(screen.getByRole("heading", { name: "Why this conclusion" })).toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "ANOMWIN-000023" })[0]);
    expect(document.getElementById("evidence-ANOMWIN-000023")).toHaveAttribute("data-active", "true");
  });

  it("renders the timeline, alternatives, similar incidents, technical notes, and actions", () => {
    render(<InvestigationScreen mode="result" view={view} />);
    expect(screen.getByRole("heading", { name: "Timeline" })).toBeInTheDocument();
    expect(screen.getByText(/not proof that it caused/i)).toBeInTheDocument();
    expect(screen.getByText("Error-rate alert opened on payment-api.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alternative causes" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Slow query or lock wait" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Similar incidents" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "HIST-007" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Technical evidence" })).toBeInTheDocument();
    expect(screen.getByText(/knowledge\/docs\/database.md/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Recommended actions" })).toBeInTheDocument();
    expect(screen.getByText(/nothing here is executed/i)).toBeInTheDocument();
  });

  it("renders the loading state as a demo preview", () => {
    render(<InvestigationScreen mode="loading" fixtureMode />);
    expect(screen.getByRole("heading", { name: "Analyzing incident" })).toBeInTheDocument();
    expect(screen.getByText(/not running against Gemini or Chroma/i)).toBeInTheDocument();
  });

  it("renders the error state without a stack trace", () => {
    render(
      <InvestigationScreen
        mode="error"
        message="The investigation service could not be reached."
        retryHref="/investigation/INC-011"
      />,
    );
    expect(screen.getByRole("heading", { name: "Investigation unavailable" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Try again" })).toHaveAttribute("href", "/investigation/INC-011");
    expect(screen.queryByText(/Traceback|GEMINI_API_KEY/)).not.toBeInTheDocument();
  });

  it("renders insufficient evidence without forcing a failure type", () => {
    render(<InvestigationScreen mode="result" view={quiet} />);
    expect(screen.getByTestId("insufficient")).toHaveTextContent("Insufficient evidence");
    expect(screen.queryByRole("heading", { name: "Database connection pool exhaustion" })).not.toBeInTheDocument();
  });
});
