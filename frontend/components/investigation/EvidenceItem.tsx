import { CopyId } from "@/components/ui/CopyId";
import { evidenceSourceLabel, formatTimestamp } from "@/lib/format";
import type { EvidenceReference, TimelineEntry } from "@/lib/types";

export function timestampFor(timeline: TimelineEntry[], evidenceId: string): string | null {
  const match = timeline.find((entry) => entry.evidence_id === evidenceId && entry.timestamp);
  return match?.timestamp ?? null;
}

export function EvidenceItem({
  item,
  timestamp,
  relationship,
  active = false,
  onSelect,
  domId,
}: {
  item: EvidenceReference;
  timestamp: string | null;
  relationship: string;
  active?: boolean;
  onSelect?: (evidenceId: string) => void;
  domId?: string;
}) {
  return (
    <article
      id={domId ?? `evidence-${item.evidence_id}`}
      className="fact-block"
      data-kind="observed-fact"
      data-active={active}
      data-source={item.source_type}
    >
      <p className="kind kind-fact">Observed fact</p>
      <p>
        {onSelect ? (
          <button type="button" className="text-button mono" onClick={() => onSelect(item.evidence_id)}>
            {item.evidence_id}
          </button>
        ) : (
          <span className="mono">{item.evidence_id}</span>
        )}
        <CopyId id={item.evidence_id} />
      </p>
      <p>Source {evidenceSourceLabel(item.source_type)}</p>
      {timestamp ? <p className="mono">{formatTimestamp(timestamp)}</p> : null}
      <p className="cause-text">{item.short_description}</p>
      <p className="meta">{relationship}</p>
    </article>
  );
}
