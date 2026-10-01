"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { RcaWorkspace } from "@/components/investigation/RcaWorkspace";
import { EmptyState } from "@/components/ui/Section";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";
import { InvestigationClientError, runInvestigation } from "@/lib/api/investigation";
import type { RCAResult } from "@/lib/types";

type Phase =
  | { phase: "idle" }
  | { phase: "investigating" }
  | { phase: "result"; result: RCAResult }
  | { phase: "error"; status: number; message: string };

const included = [
  "Loading the incident",
  "Preparing evidence",
  "Retrieving related knowledge",
  "Requesting a hypothesis",
  "Validating cited evidence",
  "Returning one RCA result",
];

export function InvestigationWorkspace({
  incidentId,
  autostart,
}: {
  incidentId: string;
  autostart: boolean;
}) {
  const [phase, setPhase] = useState<Phase>(autostart ? { phase: "investigating" } : { phase: "idle" });
  const started = useRef(false);

  function investigate() {
    setPhase({ phase: "investigating" });
    runInvestigation(incidentId)
      .then((result) => setPhase({ phase: "result", result }))
      .catch((error: unknown) => {
        const message = error instanceof InvestigationClientError ? error.message : "The investigation service could not be reached.";
        const status = error instanceof InvestigationClientError ? error.status : 0;
        setPhase({ phase: "error", status, message });
      });
  }

  useEffect(() => {
    if (!autostart || started.current) return;
    started.current = true;
    const next = `/investigations?incident=${incidentId}`;
    if (window.location.search !== `?incident=${incidentId}`) {
      window.history.replaceState(null, "", next);
    }
    investigate();
  }, [autostart, incidentId]);

  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Investigations</Kicker>
        <PageTitle>{incidentId}</PageTitle>
        {phase.phase === "idle" ? (
          <Body>
            One POST /api/incidents/investigate call returns the result. The request has not been sent.
          </Body>
        ) : null}
      </header>
      {phase.phase === "idle" ? (
        <button type="button" className="primary-action investigate-cta" onClick={investigate}>
          Investigate incident
        </button>
      ) : null}
      {phase.phase === "investigating" ? <Investigating incidentId={incidentId} /> : null}
      {phase.phase === "error" ? (
        <InvestigationFailure status={phase.status} message={phase.message} onRetry={investigate} />
      ) : null}
      {phase.phase === "result" ? <RcaWorkspace result={phase.result} /> : null}
      <Meta>
        <Link className="text-link" href={`/incidents/${incidentId}`}>
          Back to {incidentId}
        </Link>
      </Meta>
    </div>
  );
}

function Investigating({ incidentId }: { incidentId: string }) {
  return (
    <section className="section" role="status" aria-live="polite">
      <p className="kicker">Request sent</p>
      <p className="row-title">Investigating {incidentId}</p>
      <p className="pending-line">
        <span className="pending-mark" aria-hidden="true" />
        POST /api/incidents/investigate is in progress.
      </p>
      <Body>
        This endpoint is synchronous. It does not report stages as they happen. Inside the one call, the service
        does the following, then returns:
      </Body>
      <ul className="plain-list">
        {included.map((step) => (
          <li key={step}>{step}</li>
        ))}
      </ul>
    </section>
  );
}

function InvestigationFailure({
  status,
  message,
  onRetry,
}: {
  status: number;
  message: string;
  onRetry: () => void;
}) {
  const title =
    status === 404
      ? "Incident not found"
      : status === 422
        ? "Id rejected"
        : status === 503
          ? "Service not ready"
          : status === 502
            ? "Investigation failed"
            : status === 200
              ? "Response was not an RCA result"
              : "Could not reach the service";
  return (
    <div className="stack">
      <EmptyState title={title}>
        <span role="alert">{message}</span>
      </EmptyState>
      <button type="button" className="primary-action" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}
