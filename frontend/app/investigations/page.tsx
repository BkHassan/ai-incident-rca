import { InvestigationsContent } from "@/components/pages/InvestigationsContent";
import { parseIncidentId } from "@/lib/product";

export default async function InvestigationsPage({
  searchParams,
}: {
  searchParams: Promise<{ incident?: string }>;
}) {
  const { incident } = await searchParams;
  return <InvestigationsContent incidentId={parseIncidentId(incident)} />;
}
