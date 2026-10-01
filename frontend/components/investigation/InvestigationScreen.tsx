import { InvestigationDashboard } from "@/components/investigation/InvestigationDashboard";
import { InvestigationError } from "@/components/investigation/InvestigationError";
import { InvestigationLoading } from "@/components/investigation/InvestigationLoading";
import type { InvestigationView } from "@/lib/types";

export type InvestigationScreenProps =
  | { mode: "loading"; fixtureMode: boolean }
  | { mode: "error"; message: string; retryHref: string }
  | { mode: "result"; view: InvestigationView };

export function InvestigationScreen(props: InvestigationScreenProps) {
  if (props.mode === "loading") {
    return <InvestigationLoading fixtureMode={props.fixtureMode} />;
  }
  if (props.mode === "error") {
    return <InvestigationError message={props.message} retryHref={props.retryHref} />;
  }
  return <InvestigationDashboard view={props.view} />;
}
