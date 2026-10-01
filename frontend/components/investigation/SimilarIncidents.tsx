import type { SimilarIncident } from "@/lib/types";

export function SimilarIncidents({ items }: { items: SimilarIncident[] }) {
  return (
    <section aria-labelledby="similar-heading" data-testid="similar">
      <h2 id="similar-heading">Similar incidents</h2>
      <p className="meta">Retrieved notes from the result. A similar incident is not the cause of this incident.</p>
      {items.length === 0 ? (
        <p>No similar incidents were returned.</p>
      ) : (
        <div className="stack">
          {items.map((item) => (
            <article key={item.incident_id} className="fact-block" data-kind="observed-fact">
              <p className="kind kind-fact">Retrieved record</p>
              <h3 className="mono">{item.incident_id}</h3>
              <p className="cause-text">{item.similarity_note}</p>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
