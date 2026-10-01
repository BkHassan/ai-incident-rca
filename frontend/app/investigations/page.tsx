import { InvestigationsContent } from "@/components/pages/InvestigationsContent";
import { parseIncidentId } from "@/lib/product";

export default async function InvestigationsPage({
  searchParams,
}: {
  searchParams: Promise<{ incident?: string; run?: string }>;
}) {
  const { incident, run } = await searchParams;
  return <InvestigationsContent incidentId={parseIncidentId(incident)} autostart={run === "1"} />;
}
