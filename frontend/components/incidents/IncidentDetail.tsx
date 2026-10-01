"use client";

import { useEffect, useState } from "react";
import { IncidentDetailView } from "@/components/incidents/IncidentDetailView";
import { EmptyState } from "@/components/ui/Section";
import { fetchIncident, IncidentClientError } from "@/lib/api/incidents";
import type { IncidentDetail as IncidentRecord } from "@/lib/incidents";
import { parseIncidentId } from "@/lib/product";

type State =
  | { status: "loading" }
  | { status: "invalid" }
  | { status: "missing"; message: string }
  | { status: "error"; message: string }
  | { status: "ready"; incident: IncidentRecord };

export function IncidentDetail({ incidentId }: { incidentId: string }) {
  const [state, setState] = useState<State>({ status: "loading" });

  useEffect(() => {
    if (!parseIncidentId(incidentId)) {
      setState({ status: "invalid" });
      return;
    }
    let active = true;
    setState({ status: "loading" });
    fetchIncident(incidentId)
      .then((incident) => {
        if (active) setState({ status: "ready", incident });
      })
      .catch((error: unknown) => {
        if (!active) return;
        const message = error instanceof IncidentClientError ? error.message : "The incident service could not be reached.";
        const status = error instanceof IncidentClientError ? error.status : 0;
        if (status === 404) setState({ status: "missing", message });
        else setState({ status: "error", message });
      });
    return () => {
      active = false;
    };
  }, [incidentId]);

  if (state.status === "loading") return <p role="status">Loading incident</p>;
  if (state.status === "invalid") {
    return (
      <EmptyState title="Unknown incident id">
        <span role="alert">Use an id like INC-011.</span>
      </EmptyState>
    );
  }
  if (state.status === "missing") {
    return (
      <EmptyState title="Incident not found">
        <span role="alert">{state.message}</span>
      </EmptyState>
    );
  }
  if (state.status === "error") {
    return (
      <EmptyState title="Incident unavailable">
        <span role="alert">{state.message}</span>
      </EmptyState>
    );
  }
  return <IncidentDetailView incident={state.incident} />;
}
