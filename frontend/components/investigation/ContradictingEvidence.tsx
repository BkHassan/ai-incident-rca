import { EvidenceItem, timestampFor } from "@/components/investigation/EvidenceItem";
import type { EvidenceReference, TimelineEntry } from "@/lib/types";

export function ContradictingEvidence({
  items,
  timeline,
  activeId = null,
  onSelect,
}: {
  items: EvidenceReference[];
  timeline: TimelineEntry[];
  activeId?: string | null;
  onSelect?: (evidenceId: string) => void;
}) {
  return (
    <section aria-labelledby="contradicting-heading" data-testid="contradicting">
      <h2 id="contradicting-heading">Contradicting evidence</h2>
      <p className="meta">Observations the result cites against the hypothesis.</p>
      {items.length === 0 ? (
        <p>No contradicting evidence was returned.</p>
      ) : (
        <div className="stack">
          {items.map((item) => (
            <EvidenceItem
              key={item.evidence_id}
              item={item}
              timestamp={timestampFor(timeline, item.evidence_id)}
              relationship="Contradicts the hypothesis"
              active={item.evidence_id === activeId}
              onSelect={onSelect}
              domId={`evidence-${item.evidence_id}-against`}
            />
          ))}
        </div>
      )}
    </section>
  );
}
