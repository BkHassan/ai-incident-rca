import Link from "next/link";
import { EmptyState } from "@/components/ui/Section";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";

export function InvestigationsContent({ incidentId }: { incidentId: string | null }) {
  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Investigations</Kicker>
        <PageTitle>Investigation result</PageTitle>
        <Body>
          A finished investigation is one POST /api/incidents/investigate call. This section does not run that
          call and does not render a result.
        </Body>
      </header>
      {incidentId ? (
        <EmptyState title="Result not shown">
          {incidentId} is selected. This page does not call the investigation API and does not show an AI result.
          Alert metadata and observed evidence stay on the incident page.
        </EmptyState>
      ) : (
        <EmptyState title="Select an incident first">
          Investigations are opened from an incident in the catalog.
        </EmptyState>
      )}
      <Meta>
        <Link className="text-link" href={incidentId ? `/incidents/${incidentId}` : "/incidents"}>
          {incidentId ? `Back to ${incidentId}` : "Back to incidents"}
        </Link>
      </Meta>
    </div>
  );
}
