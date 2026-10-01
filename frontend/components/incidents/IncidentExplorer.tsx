"use client";

import { useEffect, useState } from "react";
import { IncidentList } from "@/components/incidents/IncidentList";
import { EmptyState } from "@/components/ui/Section";
import { Body, Kicker, PageTitle } from "@/components/ui/Type";
import { fetchIncidents, IncidentClientError } from "@/lib/api/incidents";
import type { IncidentSummary } from "@/lib/incidents";

type State =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; incidents: IncidentSummary[] };

export function IncidentExplorer() {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    let active = true;
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
  }, []);

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
      {state.status === "loading" ? <p role="status">Loading incidents</p> : null}
      {state.status === "error" ? (
        <EmptyState title="Catalog unavailable">
          <span role="alert">{state.message}</span>
        </EmptyState>
      ) : null}
      {state.status === "ready" && state.incidents.length === 0 ? (
        <EmptyState title="No incidents">The catalog response did not include any incidents.</EmptyState>
      ) : null}
      {state.status === "ready" && state.incidents.length > 0 ? <IncidentList incidents={state.incidents} /> : null}
    </div>
  );
}
