import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));
import { OverviewContent } from "@/components/pages/OverviewContent";
import { IncidentsContent } from "@/components/pages/IncidentsContent";
import { InvestigationsContent } from "@/components/pages/InvestigationsContent";
import { KnowledgeContent } from "@/components/pages/KnowledgeContent";
import { Sidebar } from "@/components/shell/Sidebar";
import { navigation } from "@/lib/product";

describe("product shell", () => {
  it("lists the four primary sections", () => {
    render(<Sidebar currentPath="/incidents" incidentId={null} />);
    for (const item of navigation) {
      expect(screen.getByRole("link", { name: new RegExp(item.label) })).toHaveAttribute(
        "href",
        item.href,
      );
    }
    expect(screen.getByRole("link", { name: /Incidents/ })).toHaveAttribute("aria-current", "page");
  });

  it("keeps the selected incident on navigation links", () => {
    render(<Sidebar currentPath="/" incidentId="INC-011" />);
    expect(screen.getByRole("link", { name: /Incidents/ })).toHaveAttribute("href", "/incidents?incident=INC-011");
  });

  it("uses incidents as the entry point and does not invent metrics", () => {
    render(<OverviewContent incidentId={null} />);
    expect(screen.getByRole("link", { name: "Open incidents" })).toHaveAttribute("href", "/incidents");
    expect(screen.queryByText(/uptime|revenue|users online|% of incidents/i)).not.toBeInTheDocument();
  });

  it("does not invent an incident record", () => {
    render(<IncidentsContent incidentId="INC-011" />);
    expect(screen.getByText("INC-011")).toBeInTheDocument();
    expect(screen.getByText(/does not read the incident file/i)).toBeInTheDocument();
    expect(screen.queryByText(/HIGH|payment-api|root cause/i)).not.toBeInTheDocument();
  });

  it("does not render an investigation result", () => {
    render(<InvestigationsContent incidentId="INC-011" />);
    expect(screen.getByText(/does not run that call/i)).toBeInTheDocument();
    expect(screen.queryByText(/Database connection pool/i)).not.toBeInTheDocument();
  });

  it("does not list knowledge documents", () => {
    render(<KnowledgeContent />);
    expect(screen.getByText(/does not list documents/i)).toBeInTheDocument();
    expect(screen.queryByText(/HIST-\d+/)).not.toBeInTheDocument();
  });
});
