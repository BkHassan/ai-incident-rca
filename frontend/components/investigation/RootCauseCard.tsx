import { formatScore } from "@/lib/format";
import { INSUFFICIENT_EVIDENCE, type RCAResult } from "@/lib/types";

export function RootCauseCard({ result }: { result: RCAResult }) {
  const insufficient = result.root_cause.cause === INSUFFICIENT_EVIDENCE;
  return (
    <section className="hypothesis-block" aria-labelledby="cause-heading" data-kind="model-hypothesis" data-testid="root-cause">
      <p className="kind kind-hypothesis">Model hypothesis</p>
      <h2 id="cause-heading" data-testid={insufficient ? "insufficient" : undefined}>
        {insufficient ? "Insufficient evidence" : result.root_cause.cause}
      </h2>
      <p className="cause-text">{result.summary}</p>
      <p>
        Uncalibrated score <span className="mono">{formatScore(result.confidence)}</span>. Not a probability.
      </p>
      <p className="cause-text">{result.root_cause.rationale}</p>
    </section>
  );
}
