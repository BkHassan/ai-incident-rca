import Link from "next/link";
import { InvestigationWorkspace } from "@/components/investigation/InvestigationWorkspace";
import { StatePanel } from "@/components/ui/StatePanel";
import { Body, Kicker, PageTitle } from "@/components/ui/Type";

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
        <StatePanel
          title="No incident selected"
          happened="An investigation needs an incident id. None is selected."
          next="Open the catalog and choose an incident."
          actions={
            <Link className="primary-action" href="/incidents">
              Open incidents
            </Link>
          }
        />
      </div>
    );
  }
  return <InvestigationWorkspace incidentId={incidentId} autostart={autostart} />;
}
