import type { RecommendedAction } from "@/lib/types";

export function RecommendedActions({
  actions,
  onSelect,
}: {
  actions: RecommendedAction[];
  onSelect: (evidenceId: string) => void;
}) {
  return (
    <section className="panel" aria-labelledby="actions-heading" data-testid="actions">
      <h2 id="actions-heading">Recommended actions</h2>
      <p className="lede">Checks for an investigator. Nothing here runs a change in production.</p>
      {actions.length === 0 ? (
        <p className="empty">No next check was returned.</p>
      ) : (
        <ol className="actions">
          {actions.map((action, index) => (
            <li key={action.action}>
              <span className="index mono">{String(index + 1).padStart(2, "0")}</span>
              <div>
                <h3>{action.action}</h3>
                <p>{action.rationale}</p>
                {action.evidence_ids.length > 0 ? (
                  <p className="event-meta">
                    {action.evidence_ids.map((id) => (
                      <button key={id} type="button" className="text-button mono" onClick={() => onSelect(id)}>
                        {id}
                      </button>
                    ))}
                  </p>
                ) : null}
              </div>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
