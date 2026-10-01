import Link from "next/link";
import { StatePanel } from "@/components/ui/StatePanel";
import { Body, Kicker, PageTitle } from "@/components/ui/Type";
import { investigationHref } from "@/lib/product";

export function KnowledgeContent({ incidentId = null }: { incidentId?: string | null }) {
  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Knowledge</Kicker>
        <PageTitle>Retrieval collections</PageTitle>
        <Body>
          Historical incidents and technical notes are retrieved for an investigation. This page does not list
          documents and it is not a chat.
        </Body>
      </header>
      {incidentId ? (
        <StatePanel
          title="Incident selected"
          happened={`Retrieval for ${incidentId} is shown on its investigation.`}
          next="Open the incident record, or start the investigation to see historical and technical matches."
          actions={
            <>
              <Link className="primary-action" href={`/incidents/${incidentId}`}>
                Open {incidentId}
              </Link>
              <Link className="text-link" href={investigationHref(incidentId)}>
                Investigate {incidentId}
              </Link>
            </>
          }
        />
      ) : (
        <StatePanel
          title="No incident selected"
          happened="Retrieval runs for one incident inside an investigation."
          next="Open the catalog and choose an incident."
          actions={
            <Link className="primary-action" href="/incidents">
              Open incidents
            </Link>
          }
        />
      )}
    </div>
  );
}
