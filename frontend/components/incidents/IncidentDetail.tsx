"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { IncidentDetailView } from "@/components/incidents/IncidentDetailView";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatePanel } from "@/components/ui/StatePanel";
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
  const [attempt, setAttempt] = useState(0);

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
  }, [incidentId, attempt]);

  if (state.status === "loading") return <Skeleton label="Loading incident" />;
  if (state.status === "invalid") {
    return (
      <StatePanel
        title="Unknown incident id"
        happened="Use an id like INC-011."
        next="Open the catalog and choose an incident."
        alert
        actions={
          <Link className="primary-action" href="/incidents">
            Open incidents
          </Link>
        }
      />
    );
  }
  if (state.status === "missing") {
    return (
      <StatePanel
        title="Incident not found"
        happened={state.message}
        next="Return to the catalog and choose an incident that exists."
        alert
        actions={
          <Link className="primary-action" href="/incidents">
            Open incidents
          </Link>
        }
      />
    );
  }
  if (state.status === "error") {
    return (
      <StatePanel
        title="Backend unavailable"
        happened={state.message}
        next="Retry this incident, or return to the catalog."
        alert
        actions={
          <>
            <button type="button" className="primary-action" onClick={() => setAttempt((value) => value + 1)}>
              Retry incident
            </button>
            <Link className="text-link" href="/incidents">
              Open incidents
            </Link>
          </>
        }
      />
    );
  }
  return <IncidentDetailView incident={state.incident} />;
}
