import { CopyId } from "@/components/ui/CopyId";
import type { EvidenceReference, RecommendedAction } from "@/lib/types";

export function RecommendedActions({
  actions,
  evidence = [],
  onSelect,
}: {
  actions: RecommendedAction[];
  evidence?: EvidenceReference[];
  onSelect?: (evidenceId: string) => void;
}) {
  const byId = new Map(evidence.map((item) => [item.evidence_id, item]));
  return (
    <section aria-labelledby="actions-heading" data-testid="actions">
      <h2 id="actions-heading">Recommended actions</h2>
      <p className="meta">
        Returned in this order. Nothing here is executed.
      </p>
      {actions.length === 0 ? (
        <p>No recommended actions were returned.</p>
      ) : (
        <ol className="stack action-list">
          {actions.map((action, index) => (
            <li key={`${index}-${action.action}`} className="action-block" data-kind="recommended-action">
              <p className="kind kind-action">Recommended action</p>
              <h3>{action.action}</h3>
              <p className="cause-text">{action.rationale}</p>
              {action.evidence_ids.length > 0 ? (
                <ul className="plain-list">
                  {action.evidence_ids.map((id) => {
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
                        <CopyId id={id} />
                        {cited ? <span> {cited.short_description}</span> : null}
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="meta">No evidence ids were returned with this action.</p>
              )}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
