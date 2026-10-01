import { formatScore } from "@/lib/format";
import type { RCAResult } from "@/lib/types";
import { isInsufficient } from "@/lib/view";

export function RootCauseCard({
  rca,
  onSelect,
}: {
  rca: RCAResult;
  onSelect: (evidenceId: string) => void;
}) {
  if (isInsufficient(rca)) {
    return (
      <section className="panel root-cause insufficient" aria-labelledby="cause-heading" data-testid="root-cause">
        <p className="kicker">Investigation result</p>
        <h2 id="cause-heading" data-testid="insufficient">
          Insufficient evidence
        </h2>
        <p>{rca.root_cause.rationale}</p>
        <p className="score-note">
          Investigation confidence <span className="mono">{formatScore(rca.confidence)}</span>. Uncalibrated score
          from 0 to 1. Not a probability.
        </p>
      </section>
    );
  }

  return (
    <section className="panel root-cause" aria-labelledby="cause-heading" data-testid="root-cause">
      <p className="kicker">Root cause hypothesis</p>
      <h2 id="cause-heading">{rca.root_cause.cause}</h2>
      <p className="score">
        <span className="score-value mono">{formatScore(rca.confidence)}</span>
        <span>
          Investigation confidence
          <small>Uncalibrated score from 0 to 1. Not a probability.</small>
        </span>
      </p>
      <p>{rca.root_cause.rationale}</p>
      <EvidenceIdList label="Supported by" ids={rca.root_cause.supporting_evidence_ids} onSelect={onSelect} />
      <EvidenceIdList label="Cut against by" ids={rca.root_cause.contradicting_evidence_ids} onSelect={onSelect} />
    </section>
  );
}

function EvidenceIdList({
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
    <div className="id-row">
      <h3>{label}</h3>
      <ul>
        {ids.map((id) => (
          <li key={id}>
            <button type="button" className="text-button mono" onClick={() => onSelect(id)}>
              {id}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
