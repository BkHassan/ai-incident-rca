import { IncidentsContent } from "@/components/pages/IncidentsContent";
import { parseIncidentId } from "@/lib/product";

export default async function IncidentsPage({
  searchParams,
}: {
  searchParams: Promise<{ incident?: string }>;
}) {
  const { incident } = await searchParams;
  return <IncidentsContent incidentId={parseIncidentId(incident)} />;
}
