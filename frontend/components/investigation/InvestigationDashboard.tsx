"use client";

import { useState } from "react";
import { AlternativeCauses } from "@/components/investigation/AlternativeCauses";
import { ContradictingEvidence } from "@/components/investigation/ContradictingEvidence";
import { EvidenceList } from "@/components/investigation/EvidenceList";
import { IncidentHeader } from "@/components/investigation/IncidentHeader";
import { InvestigationSummary } from "@/components/investigation/InvestigationSummary";
import { MetricsPanel } from "@/components/investigation/MetricsPanel";
import { RecommendedActions } from "@/components/investigation/RecommendedActions";
import { RootCauseCard } from "@/components/investigation/RootCauseCard";
import { SimilarIncidents } from "@/components/investigation/SimilarIncidents";
import { TechnicalEvidence } from "@/components/investigation/TechnicalEvidence";
import { Timeline } from "@/components/investigation/Timeline";
import type { InvestigationView } from "@/lib/types";

export function InvestigationDashboard({ view }: { view: InvestigationView }) {
  const [activeId, setActiveId] = useState<string | null>(null);

  function focusEvidence(evidenceId: string) {
    setActiveId(evidenceId);
    const node =
      document.getElementById(`evidence-${evidenceId}`) ??
      document.getElementById(`evidence-${evidenceId}-against`);
    node?.scrollIntoView?.({ block: "nearest" });
  }

  return (
    <article className="investigation">
      <IncidentHeader header={view.header} demo={view.source === "fixture"} />
      <div className="layout">
        <div className="primary">
          <InvestigationSummary summary={view.rca.summary} />
          <RootCauseCard result={view.rca} />
          <Timeline events={view.timeline} activeId={activeId} onSelect={focusEvidence} />
          <MetricsPanel series={view.metrics} demo={view.source === "fixture"} />
          <AlternativeCauses causes={view.rca.alternative_causes} evidence={[...view.rca.supporting_evidence, ...view.rca.contradicting_evidence]} onSelect={focusEvidence} />
          <RecommendedActions actions={view.rca.recommended_actions} onSelect={focusEvidence} />
        </div>
        <aside className="secondary" aria-label="Evidence and references">
          <EvidenceList items={view.rca.supporting_evidence} timeline={view.rca.timeline} activeId={activeId} onSelect={focusEvidence} />
          <ContradictingEvidence items={view.rca.contradicting_evidence} timeline={view.rca.timeline} activeId={activeId} onSelect={focusEvidence} />
          <SimilarIncidents items={view.rca.similar_incidents} />
          <TechnicalEvidence items={view.technical} />
        </aside>
      </div>
    </article>
  );
}
