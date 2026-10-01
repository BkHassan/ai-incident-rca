"use client";

import { useState } from "react";
import { AlternativeCauses } from "@/components/investigation/AlternativeCauses";
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
    document.getElementById(`evidence-${evidenceId}`)?.scrollIntoView?.({ block: "nearest" });
  }

  return (
    <article className="investigation">
      <IncidentHeader header={view.header} demo={view.source === "fixture"} />
      <div className="layout">
        <div className="primary">
          <InvestigationSummary summary={view.rca.summary} />
          <RootCauseCard rca={view.rca} onSelect={focusEvidence} />
          <Timeline events={view.timeline} activeId={activeId} onSelect={focusEvidence} />
          <MetricsPanel series={view.metrics} demo={view.source === "fixture"} />
          <AlternativeCauses causes={view.rca.alternative_causes} onSelect={focusEvidence} />
          <RecommendedActions actions={view.rca.recommended_actions} onSelect={focusEvidence} />
        </div>
        <aside className="secondary" aria-label="Evidence and references">
          <EvidenceList items={view.evidence} activeId={activeId} onSelect={focusEvidence} />
          <SimilarIncidents items={view.historical} />
          <TechnicalEvidence items={view.technical} />
        </aside>
      </div>
    </article>
  );
}
