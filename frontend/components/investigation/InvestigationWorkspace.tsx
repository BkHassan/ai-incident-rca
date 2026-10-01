"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { RcaWorkspace } from "@/components/investigation/RcaWorkspace";
import { RetrievalContext } from "@/components/investigation/RetrievalContext";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatePanel } from "@/components/ui/StatePanel";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";
import { InvestigationClientError, runInvestigation } from "@/lib/api/investigation";
import { loadRetrieval, RetrievalClientError } from "@/lib/api/retrieval";
import type { RetrievalOrigin, RetrievalPayload } from "@/lib/retrieval";
import { INSUFFICIENT_EVIDENCE, type RCAResult } from "@/lib/types";

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
  const [retrieval, setRetrieval] = useState<{
    origin: RetrievalOrigin | "loading" | "error";
    payload: RetrievalPayload | null;
    error: string | null;
  }>({ origin: "loading", payload: null, error: null });
  const [retrievalAttempt, setRetrievalAttempt] = useState(0);
  const started = useRef(false);

  useEffect(() => {
    let cancelled = false;
    setRetrieval({ origin: "loading", payload: null, error: null });
    loadRetrieval(incidentId)
      .then((loaded) => {
        if (!cancelled) setRetrieval({ origin: loaded.origin, payload: loaded.payload, error: null });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        const message = error instanceof RetrievalClientError ? error.message : "The retrieval service could not be reached.";
        setRetrieval({ origin: "error", payload: null, error: message });
      });
    return () => {
      cancelled = true;
    };
  }, [incidentId, retrievalAttempt]);

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
      </header>
      <InvestigationStatus incidentId={incidentId} phase={phase} retrievalFailed={retrieval.origin === "error"} />
      <RetrievalContext
        incidentId={incidentId}
        origin={retrieval.origin}
        payload={retrieval.payload}
        error={retrieval.error}
        onRetry={() => setRetrievalAttempt((value) => value + 1)}
      />
      {phase.phase === "idle" ? (
        <button type="button" className="primary-action investigate-cta" onClick={investigate}>
          Investigate incident
        </button>
      ) : null}
      {phase.phase === "investigating" ? (
        <>
          <Skeleton label="Investigation running" lines={5} />
          <Investigating incidentId={incidentId} />
        </>
      ) : null}
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

function InvestigationStatus({
  incidentId,
  phase,
  retrievalFailed,
}: {
  incidentId: string;
  phase: Phase;
  retrievalFailed: boolean;
}) {
  const insufficient = phase.phase === "result" && phase.result.root_cause.cause === INSUFFICIENT_EVIDENCE;
  const partial = phase.phase === "result" && retrievalFailed;
  let label = "Investigation ready";
  let happened = `The investigation request for ${incidentId} has not been sent.`;
  let next = "Read the retrieval context, then investigate this incident.";
  if (phase.phase === "investigating") {
    label = "Investigation running";
    happened = `One request for ${incidentId} is in progress. The service does not report intermediate stages.`;
    next = "Stay on this page until a result or a failure returns.";
  } else if (phase.phase === "error") {
    const backend = phase.status === 503 || phase.status === 0;
    return (
      <section
        className="section"
        aria-label="Investigation status"
        data-investigation-status={backend ? "Backend unavailable" : "Investigation failed"}
      >
        {backend ? <p className="kicker">Backend unavailable</p> : null}
      </section>
    );
  } else if (insufficient) {
    label = "Insufficient evidence";
    happened = "The result returned and did not name a cause.";
    next = "Read the recommended actions. They describe what to collect next.";
  } else if (partial) {
    label = "Partial result";
    happened = "The hypothesis returned. Retrieval did not.";
    next = "Read the findings below, then retry retrieval.";
  } else if (phase.phase === "result") {
    label = "Investigation succeeded";
    happened = "Findings are the model hypothesis. Evidence rows are observed facts. Actions are recommendations.";
    next = "Read findings, then evidence, then actions. Nothing on this page is executed.";
  }
  return (
    <section className="section" aria-label="Investigation status" data-investigation-status={label}>
      <p className="kicker">{label}</p>
      <Body>{happened}</Body>
      <Meta>Next: {next}</Meta>
    </section>
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
  const backend = status === 503 || status === 0;
  const next =
    status === 404
      ? "Return to the catalog and choose an incident that exists."
      : status === 422
        ? "Open an incident from the catalog. Ids look like INC-011."
        : backend
          ? "Retry after the service is reachable, or go back to the incident."
          : "Retry the investigation. The previous request did not return a usable result.";
  return (
    <StatePanel
      title={title}
      happened={message}
      next={next}
      alert
      actions={
        <button type="button" className="primary-action" onClick={onRetry}>
          Try again
        </button>
      }
    />
  );
}
