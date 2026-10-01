"use client";

import { useState } from "react";
import { CopyId } from "@/components/ui/CopyId";
import { Section } from "@/components/ui/Section";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatePanel } from "@/components/ui/StatePanel";
import { Meta } from "@/components/ui/Type";
import { formatScore } from "@/lib/format";
import type { HistoricalHit, RetrievalOrigin, RetrievalPayload, TechnicalHit } from "@/lib/retrieval";
import { previewText } from "@/lib/retrieval";

export function RetrievalContext({
  incidentId,
  origin,
  payload,
  error,
  onRetry,
}: {
  incidentId: string;
  origin: RetrievalOrigin | "loading" | "error";
  payload: RetrievalPayload | null;
  error: string | null;
  onRetry?: () => void;
}) {
  return (
    <div className="stack">
      <ol className="retrieval-flow">
        <li>
          <span className="type-label">Current incident</span>
          <span className="mono">{incidentId}</span>
        </li>
        <li>
          <span className="type-label">Retrieval</span>
          <span>Historical incidents and technical documents for this incident</span>
        </li>
        <li>
          <span className="type-label">Historical / technical context</span>
          <span>Records returned for the observational query</span>
        </li>
        <li>
          <span className="type-label">Investigation</span>
          <span>The hypothesis is requested separately, after this context</span>
        </li>
      </ol>
      {origin === "fixture" ? (
        <p className="fixture-banner" role="status">
          Fixture / dev data. These records were not retrieved from the index.
        </p>
      ) : null}
      {origin === "loading" ? <Skeleton label="Loading retrieval" lines={3} /> : null}
      {origin === "error" ? (
        <StatePanel
          title="Backend unavailable"
          happened={error ?? "Retrieval did not return."}
          next="Retry retrieval. Starting an investigation is a separate request."
          alert
          actions={
            onRetry ? (
              <button type="button" className="primary-action" onClick={onRetry}>
                Retry retrieval
              </button>
            ) : null
          }
        />
      ) : null}
      {payload ? (
        <>
          <Meta>Observational query: {payload.query}</Meta>
          <HistoricalIncidents items={payload.historical_incidents} />
          <TechnicalKnowledge items={payload.technical_documents} />
        </>
      ) : null}
    </div>
  );
}

function HistoricalIncidents({ items }: { items: HistoricalHit[] }) {
  return (
    <Section id="similar-historical" title="Similar historical incidents">
      <Meta>Historical knowledge. A past incident is background for this investigation. Its recorded cause is not the cause of the current incident.</Meta>
      {items.length === 0 ? (
        <StatePanel
          title="No historical matches"
          happened="Retrieval returned no prior incidents for this query."
          next="Continue with the observed evidence. A historical match is not required to investigate."
        />
      ) : (
        <div className="stack">
          {items.map((item) => (
            <HistoricalCard key={item.incident_id} item={item} />
          ))}
        </div>
      )}
    </Section>
  );
}

function HistoricalCard({ item }: { item: HistoricalHit }) {
  const [open, setOpen] = useState(false);
  const context = [item.service, item.occurred_at, item.severity].filter(Boolean).join(" · ");
  return (
    <article className="fact-block">
      <p className="kind kind-fact">Historical</p>
      <h3 className="mono">{item.incident_id}</h3>
      <CopyId id={item.incident_id} />
      <p className="meta">
        Rank {item.rank} · cosine similarity {formatScore(item.score)}
        {context ? ` · ${context}` : ""}
      </p>
      <p className="cause-text">{open ? item.text : previewText(item.text)}</p>
      {item.text.length > 280 ? (
        <button type="button" className="text-button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? "Hide retrieved text" : "Show retrieved text"}
        </button>
      ) : null}
      {item.historical_root_cause ? (
        <div>
          <p className="type-label">Historical root cause</p>
          <p>
            {item.historical_root_cause}
            {item.historical_root_cause_service ? ` · ${item.historical_root_cause_service}` : ""}
          </p>
          <Meta>Recorded for {item.incident_id}. It is not the cause of the current incident.</Meta>
        </div>
      ) : null}
    </article>
  );
}

function TechnicalKnowledge({ items }: { items: TechnicalHit[] }) {
  return (
    <Section id="technical-knowledge" title="Technical knowledge">
      <Meta>Retrieved document chunks. They describe mechanisms. They are not observations from this incident.</Meta>
      {items.length === 0 ? (
        <StatePanel
          title="No technical-document matches"
          happened="Retrieval returned no document chunks for this query."
          next="Continue with the logs, metrics, and anomalies from this incident."
        />
      ) : (
        <div className="stack">
          {items.map((item) => (
            <TechnicalCard key={item.document_id} item={item} />
          ))}
        </div>
      )}
    </Section>
  );
}

function TechnicalCard({ item }: { item: TechnicalHit }) {
  const [open, setOpen] = useState(false);
  return (
    <article className="fact-block">
      <p className="kind kind-fact">Technical</p>
      <h3>{item.title}</h3>
      <p>
        {item.section} · <span className="mono">{item.document_id}</span>
        {item.document_name ? ` · ${item.document_name}` : ""}
      </p>
      <p className="meta">
        Rank {item.rank} · cosine similarity {formatScore(item.score)}
      </p>
      <p className="cause-text">{open ? item.text : previewText(item.text)}</p>
      {item.text.length > 280 ? (
        <button type="button" className="text-button" aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? "Hide chunk" : "Show chunk"}
        </button>
      ) : null}
    </article>
  );
}
