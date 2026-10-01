import Link from "next/link";
import { IncidentPicker } from "@/components/incidents/IncidentPicker";
import { EmptyState, Section } from "@/components/ui/Section";
import { Body, Kicker, PageTitle } from "@/components/ui/Type";
import { hrefWithIncident } from "@/lib/product";

export function IncidentsContent({ incidentId }: { incidentId: string | null }) {
  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Incidents</Kicker>
        <PageTitle>Select an incident</PageTitle>
        <Body>
          There is no incident list endpoint. Choose an id in the form the investigation API already accepts.
          This page does not read the incident file, so it will not show a title, severity, or service.
        </Body>
      </header>
      <Section id="select-incident" title="Incident id">
        <IncidentPicker current={incidentId} />
      </Section>
      {incidentId ? (
        <Section id="selected-incident" title="Selected">
          <p className="mono selected-id">{incidentId}</p>
          <Body>
            Context for this id is not exposed yet. The next product step is the investigation view, which is
            not built here.
          </Body>
          <Link className="text-link" href={hrefWithIncident("/investigations", incidentId)}>
            View investigations section
          </Link>
        </Section>
      ) : (
        <EmptyState title="No incident selected">
          Enter an id such as INC-011. Nothing is loaded until an investigation view exists.
        </EmptyState>
      )}
    </div>
  );
}
