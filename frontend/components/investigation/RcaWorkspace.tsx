"use client";

import { useState } from "react";
import { Section } from "@/components/ui/Section";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";
import { formatScore } from "@/lib/format";
import { INSUFFICIENT_EVIDENCE, type RCAResult } from "@/lib/types";

export function RcaWorkspace({ result }: { result: RCAResult }) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const insufficient = result.root_cause.cause === INSUFFICIENT_EVIDENCE;

  function focusEvidence(evidenceId: string) {
    setActiveId(evidenceId);
    document.getElementById(`evidence-${evidenceId}`)?.scrollIntoView?.({ block: "nearest" });
  }

  return (
    <div className="stack">
      <header className="page-head">
        <Kicker>Result returned</Kicker>
        <PageTitle>{result.incident_id}</PageTitle>
        <Body>{result.summary}</Body>
        <Meta>This is the AI investigation result. It is separate from the alert metadata and the observed evidence.</Meta>
      </header>
      <Section id="hypothesis" title={insufficient ? "Insufficient evidence" : "Root-cause hypothesis"}>
        {insufficient ? (
          <Body>{result.root_cause.rationale}</Body>
        ) : (
          <>
            <p className="row-title">{result.root_cause.cause}</p>
            <Body>{result.root_cause.rationale}</Body>
            <EvidenceLinks label="Supporting ids" ids={result.root_cause.supporting_evidence_ids} onSelect={focusEvidence} />
            <EvidenceLinks label="Contradicting ids" ids={result.root_cause.contradicting_evidence_ids} onSelect={focusEvidence} />
          </>
        )}
        <Meta>
          Uncalibrated score {formatScore(result.confidence)}. This is not a probability.
        </Meta>
      </Section>
      {result.alternative_causes.length > 0 ? (
        <Section id="alternatives" title="Alternative causes">
          <ul className="evidence-list">
            {result.alternative_causes.map((cause) => (
              <li key={cause.cause}>
                <span className="row-title">
                  {cause.cause === INSUFFICIENT_EVIDENCE ? "Insufficient evidence" : cause.cause}
                </span>
                <span>{cause.rationale}</span>
                <Meta>Uncalibrated score {formatScore(cause.confidence)}</Meta>
              </li>
            ))}
          </ul>
        </Section>
      ) : null}
      <Section id="supporting-evidence" title="Supporting evidence">
        <EvidenceRows items={result.supporting_evidence} activeId={activeId} onSelect={focusEvidence} empty="None cited." />
      </Section>
      <Section id="contradicting-evidence" title="Contradicting evidence">
        <EvidenceRows items={result.contradicting_evidence} activeId={activeId} onSelect={focusEvidence} empty="None cited." />
      </Section>
      <Section id="cited-timeline" title="Cited timeline">
        <Meta>Entries are citations on the result. Order here is the result timeline, not a claim of causation.</Meta>
        {result.timeline.length === 0 ? (
          <Body>No timeline entries.</Body>
        ) : (
          <ol className="timeline-list">
            {result.timeline.map((entry) => (
              <li key={`${entry.evidence_id}-${entry.timestamp}`}>
                <button type="button" className="text-button mono" onClick={() => focusEvidence(entry.evidence_id)}>
                  {entry.evidence_id}
                </button>
                <span>{entry.description}</span>
                <Meta>{entry.timestamp || "No timestamp"}</Meta>
              </li>
            ))}
          </ol>
        )}
      </Section>
      <Section id="actions" title="Recommended actions">
        {result.recommended_actions.length === 0 ? (
          <Body>No actions.</Body>
        ) : (
          <ul className="evidence-list">
            {result.recommended_actions.map((action) => (
              <li key={action.action}>
                <span className="row-title">{action.action}</span>
                <span>{action.rationale}</span>
                <EvidenceLinks label="Evidence" ids={action.evidence_ids} onSelect={focusEvidence} />
              </li>
            ))}
          </ul>
        )}
      </Section>
      <Section id="similar" title="Similar incidents">
        <Meta>Historical notes are background. They are not the cause of this incident.</Meta>
        {result.similar_incidents.length === 0 ? (
          <Body>None returned.</Body>
        ) : (
          <ul className="evidence-list">
            {result.similar_incidents.map((item) => (
              <li key={item.incident_id}>
                <span className="mono">{item.incident_id}</span>
                <span>{item.similarity_note}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>
    </div>
  );
}

function EvidenceLinks({
  label,
  ids,
  onSelect,
}: {
  label: string;
  ids: string[];
  onSelect: (evidenceId: string) => void;
}) {
  if (ids.length === 0) return null;
  return (
    <p className="meta">
      {label}{" "}
      {ids.map((id) => (
        <button key={id} type="button" className="text-button mono" onClick={() => onSelect(id)}>
          {id}
        </button>
      ))}
    </p>
  );
}

function EvidenceRows({
  items,
  activeId,
  onSelect,
  empty,
}: {
  items: RCAResult["supporting_evidence"];
  activeId: string | null;
  onSelect: (evidenceId: string) => void;
  empty: string;
}) {
  if (items.length === 0) return <Body>{empty}</Body>;
  return (
    <ul className="evidence-list">
      {items.map((item) => (
        <li key={item.evidence_id} id={`evidence-${item.evidence_id}`} data-active={activeId === item.evidence_id}>
          <button type="button" className="text-button mono" onClick={() => onSelect(item.evidence_id)}>
            {item.evidence_id}
          </button>
          <span className="badge badge-neutral">{item.source_type}</span>
          <span>{item.short_description}</span>
        </li>
      ))}
    </ul>
  );
}
