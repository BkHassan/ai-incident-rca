"use client";

import { useEffect, useState } from "react";
import { IncidentList } from "@/components/incidents/IncidentList";
import { EmptyState } from "@/components/ui/Section";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatePanel } from "@/components/ui/StatePanel";
import { Body, Kicker, PageTitle } from "@/components/ui/Type";
import { fetchIncidents, IncidentClientError } from "@/lib/api/incidents";
import type { IncidentSummary } from "@/lib/incidents";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; incidents: IncidentSummary[] };

export function IncidentExplorer() {
  const [state, setState] = useState<State>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    setState({ status: "loading" });
    fetchIncidents()
      .then((incidents) => {
        if (active) setState({ status: "ready", incidents });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const message = error instanceof IncidentClientError ? error.message : "The incident service could not be reached.";
        setState({ status: "error", message });
      });
    return () => {
      active = false;
    };
  }, [attempt]);

  return (
    <div className="stack explorer">
      <header className="page-head">
        <Kicker>Incidents</Kicker>
        <PageTitle>Incident catalog</PageTitle>
        <Body>
          These are alert records. Search and filters use the incident id, title, alerting service, severity,
          and description. An investigation result is a separate step.
        </Body>
      </header>
      {state.status === "loading" ? <Skeleton label="Loading incidents" /> : null}
      {state.status === "error" ? (
        <StatePanel
          title="Backend unavailable"
          happened={state.message}
          next="Retry the catalog request. Incident records are not cached in this page."
          alert
          actions={
            <button type="button" className="primary-action" onClick={() => setAttempt((value) => value + 1)}>
              Retry catalog
            </button>
          }
        />
      ) : null}
      {state.status === "ready" && state.incidents.length === 0 ? (
        <EmptyState title="No incidents">
          The catalog response did not include any incidents. Retry after incident files are available.
        </EmptyState>
      ) : null}
      {state.status === "ready" && state.incidents.length > 0 ? <IncidentList incidents={state.incidents} /> : null}
    </div>
  );
}
