import { redirect } from "next/navigation";
import { parseIncidentId } from "@/lib/product";

export default async function InvestigationRedirect({
  params,
}: {
  params: Promise<{ incidentId: string }>;
}) {
  const { incidentId } = await params;
  const id = parseIncidentId(incidentId);
  redirect(id ? `/investigations?incident=${id}` : "/investigations");
}
