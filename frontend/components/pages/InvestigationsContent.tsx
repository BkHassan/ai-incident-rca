import Link from "next/link";
import { EmptyState } from "@/components/ui/Section";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";
import { hrefWithIncident } from "@/lib/product";

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
        <EmptyState title="Not built in this step">
          {incidentId} is selected. The result view, evidence, timeline, and actions are the next feature. They
          are not shown here.
        </EmptyState>
      ) : (
        <EmptyState title="Select an incident first">
          Investigations are opened from an incident id.
        </EmptyState>
      )}
      <Meta>
        <Link className="text-link" href={hrefWithIncident("/incidents", incidentId)}>
          Back to incidents
        </Link>
      </Meta>
    </div>
  );
}
