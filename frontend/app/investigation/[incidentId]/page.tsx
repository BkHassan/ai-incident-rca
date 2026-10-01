import { InvestigationScreen } from "@/components/investigation/InvestigationScreen";
import {
  investigationSource,
  loadInvestigationView,
  publicErrorMessage,
} from "@/lib/api/investigation";

const INCIDENT_ID = /^INC-\d{3}$/;

export default async function InvestigationPage({
  params,
  searchParams,
}: {
  params: Promise<{ incidentId: string }>;
  searchParams: Promise<{ preview?: string }>;
}) {
  const { incidentId } = await params;
  const { preview } = await searchParams;
  const retryHref = `/investigation/${incidentId}`;

  if (preview === "loading") {
    return <InvestigationScreen mode="loading" fixtureMode={investigationSource() === "fixture"} />;
  }
  if (preview === "error") {
    return (
      <InvestigationScreen
        mode="error"
        message="The investigation service could not be reached."
        retryHref={retryHref}
      />
    );
  }
  if (!INCIDENT_ID.test(incidentId)) {
    return (
      <InvestigationScreen
        mode="error"
        message="Incident id must look like INC-011."
        retryHref="/investigation/INC-011"
      />
    );
  }

  try {
    const view = await loadInvestigationView(incidentId);
    return <InvestigationScreen mode="result" view={view} />;
  } catch (error) {
    return <InvestigationScreen mode="error" message={publicErrorMessage(error)} retryHref={retryHref} />;
  }
}
