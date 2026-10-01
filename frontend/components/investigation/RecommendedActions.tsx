import type { RecommendedAction } from "@/lib/types";

export function RecommendedActions({
  actions,
  onSelect,
}: {
  actions: RecommendedAction[];
  onSelect?: (evidenceId: string) => void;
}) {
  return (
    <section aria-labelledby="actions-heading" data-testid="actions">
      <h2 id="actions-heading">Recommended actions</h2>
      <p className="meta">Actions from the result. They are not observations, and nothing here is executed.</p>
      {actions.length === 0 ? (
        <p>No recommended actions were returned.</p>
      ) : (
        <ol className="stack">
          {actions.map((action) => (
            <li key={action.action} className="action-block" data-kind="recommended-action">
              <p className="kind kind-action">Recommended action</p>
              <h3>{action.action}</h3>
              <p className="cause-text">{action.rationale}</p>
              {action.evidence_ids.length > 0 ? (
                <p>
                  {action.evidence_ids.map((id) =>
                    onSelect ? (
                      <button key={id} type="button" className="text-button mono" onClick={() => onSelect(id)}>
                        {id}
                      </button>
                    ) : (
                      <span key={id} className="mono">
                        {id}
                      </span>
                    ),
                  )}
                </p>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
