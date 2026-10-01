import { KnowledgeContent } from "@/components/pages/KnowledgeContent";
import { parseIncidentId } from "@/lib/product";

export default async function KnowledgePage({
  searchParams,
}: {
  searchParams: Promise<{ incident?: string }>;
}) {
  const { incident } = await searchParams;
  return <KnowledgeContent incidentId={parseIncidentId(incident)} />;
}
