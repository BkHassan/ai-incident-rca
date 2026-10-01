import { formatScore } from "@/lib/format";
import type { RootCauseHypothesis } from "@/lib/types";

export function AlternativeCauses({
  causes,
  onSelect,
}: {
  causes: RootCauseHypothesis[];
  onSelect: (evidenceId: string) => void;
}) {
  return (
    <section className="panel" aria-labelledby="alternatives-heading" data-testid="alternatives">
      <h2 id="alternatives-heading">Alternative causes</h2>
      <p className="lede">Other hypotheses that remain plausible. They are not established causes.</p>
      {causes.length === 0 ? (
        <p className="empty">No alternative hypothesis was returned.</p>
      ) : (
        <ol className="causes">
          {causes.map((cause) => (
            <li key={cause.cause}>
              <h3>{cause.cause}</h3>
              <p className="score-note">
                Uncalibrated score <span className="mono">{formatScore(cause.confidence)}</span>. Not a rank and not a
                probability.
              </p>
              <p>{cause.rationale}</p>
              <p className="event-meta">
                {cause.supporting_evidence_ids.map((id) => (
                  <button key={id} type="button" className="text-button mono" onClick={() => onSelect(id)}>
                    {id}
                  </button>
                ))}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
