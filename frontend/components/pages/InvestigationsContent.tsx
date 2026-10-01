import Link from "next/link";
import { InvestigationWorkspace } from "@/components/investigation/InvestigationWorkspace";
import { EmptyState } from "@/components/ui/Section";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";

export function InvestigationsContent({
  incidentId,
  autostart = false,
}: {
  incidentId: string | null;
  autostart?: boolean;
}) {
  if (!incidentId) {
    return (
      <div className="stack">
        <header className="page-head">
          <Kicker>Investigations</Kicker>
          <PageTitle>Investigation</PageTitle>
          <Body>Choose an incident, then start one POST /api/incidents/investigate call.</Body>
        </header>
        <EmptyState title="Select an incident first">
          Investigations are opened from an incident in the catalog.
        </EmptyState>
        <Meta>
          <Link className="text-link" href="/incidents">
            Back to incidents
          </Link>
        </Meta>
      </div>
    );
  }
  return <InvestigationWorkspace incidentId={incidentId} autostart={autostart} />;
}
