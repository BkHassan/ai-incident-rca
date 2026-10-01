import { evidenceSourceLabel, formatTimestamp } from "@/lib/format";
import type { EvidenceCardModel } from "@/lib/types";

export function EvidenceCard({
  item,
  active,
  onSelect,
}: {
  item: EvidenceCardModel;
  active: boolean;
  onSelect: (evidenceId: string) => void;
}) {
  return (
    <article
      id={`evidence-${item.evidence_id}`}
      className="evidence-card"
      data-active={active}
      data-role={item.role}
      data-source={item.source_type}
    >
      <header>
        <button type="button" className="text-button mono" onClick={() => onSelect(item.evidence_id)}>
          {item.evidence_id}
        </button>
        <span className="pill">{evidenceSourceLabel(item.source_type)}</span>
      </header>
      <p className="evidence-role">{item.role === "supporting" ? "Supporting evidence" : "Contradicting evidence"}</p>
      <dl>
        <div>
          <dt>Timestamp</dt>
          <dd className="mono">{formatTimestamp(item.timestamp)}</dd>
        </div>
        <div>
          <dt>Service</dt>
          <dd>{item.service || "—"}</dd>
        </div>
      </dl>
      <p>{item.description}</p>
      <p className="why">
        <span>Why it matters. </span>
        {item.why_it_matters}
      </p>
    </article>
  );
}

export function EvidenceList({
  items,
  activeId,
  onSelect,
}: {
  items: EvidenceCardModel[];
  activeId: string | null;
  onSelect: (evidenceId: string) => void;
}) {
  const operational = items.filter((item) => item.source_type !== "TECHNICAL_DOCUMENT");
  return (
    <section className="panel" aria-labelledby="evidence-heading" data-testid="evidence-list">
      <h2 id="evidence-heading">Key evidence</h2>
      <p className="lede">Cited observations. Technical notes are expanded in their own section.</p>
      {operational.length === 0 ? (
        <p className="empty">No operational evidence was cited.</p>
      ) : (
        <div className="stack">
          {operational.map((item) => (
            <EvidenceCard key={`${item.role}-${item.evidence_id}`} item={item} active={item.evidence_id === activeId} onSelect={onSelect} />
          ))}
        </div>
      )}
    </section>
  );
}
