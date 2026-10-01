import { OverviewContent } from "@/components/pages/OverviewContent";
import { parseIncidentId } from "@/lib/product";

export default async function OverviewPage({
  searchParams,
}: {
  searchParams: Promise<{ incident?: string }>;
}) {
  const { incident } = await searchParams;
  return <OverviewContent incidentId={parseIncidentId(incident)} />;
}
