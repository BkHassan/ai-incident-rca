import Link from "next/link";
import { Card, Section } from "@/components/ui/Section";
import { Badge } from "@/components/ui/Badge";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";
import { hrefWithIncident } from "@/lib/product";

const returnedFields = [
  "Summary",
  "Root-cause hypothesis",
  "Uncalibrated confidence",
  "Alternative causes",
  "Supporting and contradicting evidence ids",
  "Cited timeline",
  "Recommended actions",
  "Similar-incident notes",
  "Insufficient-evidence result",
];

export function OverviewContent({ incidentId }: { incidentId: string | null }) {
  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Overview</Kicker>
        <PageTitle>Investigate one incident</PageTitle>
        <Body>
          This console is the entry to root-cause investigation. Start from the incident catalog. Investigate
          sends one request and shows the RCA result that comes back.
        </Body>
      </header>
      <Card>
        <Kicker>Next step</Kicker>
        <p className="card-title">Incidents</p>
        <Body>The catalog is the operational entry. Choose an incident, then open it before starting an investigation.</Body>
        <Link className="text-link" href={hrefWithIncident("/incidents", incidentId)}>
          Open incidents
        </Link>
      </Card>
      <Section id="returns" title="What a completed investigation returns">
        <Body>
          When POST /api/incidents/investigate succeeds, the body is one RCA result. These are fields of that
          response, not metrics collected by this page.
        </Body>
        <ul className="plain-list">
          {returnedFields.map((field) => (
            <li key={field}>{field}</li>
          ))}
        </ul>
        <Meta>Confidence is an uncalibrated score from 0 to 1, not a probability.</Meta>
      </Section>
      <Section id="unavailable" title="Not available from the API">
        <ul className="plain-list">
          <li>
            <Badge tone="neutral">Catalog</Badge> Titles, alert severity, and the alerting service are on Incidents
          </li>
          <li>
            <Badge tone="neutral">Evidence</Badge> Log counts, metric series names, detector windows, and the
            observational timeline are on the incident page. Charts are not.
          </li>
          <li>
            <Badge tone="neutral">No route</Badge> Knowledge document browser
          </li>
          <li>
            <Badge tone="attention">Blocked</Badge> A live result, until the Chroma store and Gemini access exist
          </li>
        </ul>
      </Section>
    </div>
  );
}
