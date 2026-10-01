import { reviewSummary } from "@/lib/review";
import type { RCAResult } from "@/lib/types";

export function OperationalSummary({ result }: { result: RCAResult }) {
  const review = reviewSummary(result);
  return (
    <section className="section review-sheet" aria-labelledby="investigation-summary" data-testid="operational-summary">
      <h2 id="investigation-summary">Investigation summary</h2>
      <p className="meta">Counts and text below are taken from this result.</p>
      <p className="cause-text">{review.summary}</p>
      <dl className="review-list">
        <div>
          <dt>Root cause</dt>
          <dd>{review.rootCause}</dd>
        </div>
        <div>
          <dt>Supporting evidence</dt>
          <dd>{review.supportingCount}</dd>
        </div>
        <div>
          <dt>Contradicting evidence</dt>
          <dd>{review.contradictingCount}</dd>
        </div>
        <div>
          <dt>Alternative hypotheses</dt>
          <dd>
            {review.alternatives.length === 0
              ? "0"
              : `${review.alternatives.length}: ${review.alternatives.join("; ")}`}
          </dd>
        </div>
        <div>
          <dt>Historical context</dt>
          <dd>{review.historicalCount}</dd>
        </div>
        <div>
          <dt>Technical knowledge</dt>
          <dd>{review.technicalCount}</dd>
        </div>
        <div>
          <dt>Recommended actions</dt>
          <dd>{review.actionCount}</dd>
        </div>
      </dl>
    </section>
  );
}
