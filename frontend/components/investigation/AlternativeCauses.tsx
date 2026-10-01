import { formatScore } from "@/lib/format";
import { INSUFFICIENT_EVIDENCE, type EvidenceReference, type RootCauseHypothesis } from "@/lib/types";

export function AlternativeCauses({
  causes,
  evidence,
  onSelect,
}: {
  causes: RootCauseHypothesis[];
  evidence: EvidenceReference[];
  onSelect?: (evidenceId: string) => void;
}) {
  const byId = new Map(evidence.map((item) => [item.evidence_id, item]));
  return (
    <section aria-labelledby="alternatives-heading" data-testid="alternatives">
      <h2 id="alternatives-heading">Alternative causes</h2>
      <p className="meta">Other hypotheses on the result. They are not the primary conclusion.</p>
      {causes.length === 0 ? (
        <p>No alternative causes were returned.</p>
      ) : (
        <ol className="stack">
          {causes.map((cause) => (
            <li key={cause.cause} className="hypothesis-block" data-kind="model-hypothesis">
              <p className="kind kind-hypothesis">Model hypothesis</p>
              <h3>{cause.cause === INSUFFICIENT_EVIDENCE ? "Insufficient evidence" : cause.cause}</h3>
              <p>
                Uncalibrated score <span className="mono">{formatScore(cause.confidence)}</span>. Not a probability.
              </p>
              <p className="cause-text">{cause.rationale}</p>
              {cause.supporting_evidence_ids.length === 0 ? (
                <p className="meta">No supporting evidence ids on this hypothesis.</p>
              ) : (
                <ul className="plain-list">
                  {cause.supporting_evidence_ids.map((id) => {
                    const cited = byId.get(id);
                    return (
                      <li key={id}>
                        {onSelect ? (
                          <button type="button" className="text-button mono" onClick={() => onSelect(id)}>
                            {id}
                          </button>
                        ) : (
                          <span className="mono">{id}</span>
                        )}
                        {cited ? <span> {cited.short_description}</span> : null}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
