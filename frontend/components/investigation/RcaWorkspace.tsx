"use client";

import { useState } from "react";
import { AlternativeCauses } from "@/components/investigation/AlternativeCauses";
import { ContradictingEvidence } from "@/components/investigation/ContradictingEvidence";
import { EvidenceList } from "@/components/investigation/EvidenceList";
import { RCAHeader } from "@/components/investigation/RCAHeader";
import { RecommendedActions } from "@/components/investigation/RecommendedActions";
import { RootCauseCard } from "@/components/investigation/RootCauseCard";
import { SimilarIncidents } from "@/components/investigation/SimilarIncidents";
import type { RCAResult } from "@/lib/types";

export function RcaWorkspace({ result }: { result: RCAResult }) {
  const [activeId, setActiveId] = useState<string | null>(null);
  const evidence = [...result.supporting_evidence, ...result.contradicting_evidence];

  function focusEvidence(evidenceId: string) {
    setActiveId(evidenceId);
    const node =
      document.getElementById(`evidence-${evidenceId}`) ??
      document.getElementById(`evidence-${evidenceId}-against`);
    node?.scrollIntoView?.({ block: "nearest" });
  }

  return (
    <div className="stack workspace">
      <RCAHeader incidentId={result.incident_id} />
      <RootCauseCard result={result} />
      <EvidenceList
        items={result.supporting_evidence}
        timeline={result.timeline}
        activeId={activeId}
        onSelect={focusEvidence}
      />
      <ContradictingEvidence
        items={result.contradicting_evidence}
        timeline={result.timeline}
        activeId={activeId}
        onSelect={focusEvidence}
      />
      <AlternativeCauses causes={result.alternative_causes} evidence={evidence} onSelect={focusEvidence} />
      <SimilarIncidents items={result.similar_incidents} />
      <RecommendedActions actions={result.recommended_actions} onSelect={focusEvidence} />
    </div>
  );
}
