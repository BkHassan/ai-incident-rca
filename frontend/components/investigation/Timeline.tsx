import { formatTimestamp } from "@/lib/format";
import type { TimelineEventModel } from "@/lib/types";

const KIND_LABEL = {
  observation: "Observation",
  anomaly: "Anomaly",
  error: "Error",
  investigation: "Investigation",
} as const;

export function Timeline({
  events,
  activeId,
  onSelect,
}: {
  events: TimelineEventModel[];
  activeId: string | null;
  onSelect: (evidenceId: string) => void;
}) {
  return (
    <section className="panel" aria-labelledby="timeline-heading" data-testid="timeline">
      <h2 id="timeline-heading">Timeline</h2>
      <p className="lede">
        Recorded order only. An earlier event is not proof that it caused a later one.
      </p>
      {events.length === 0 ? (
        <p className="empty">No timeline entries were returned.</p>
      ) : (
        <ol className="timeline">
          {events.map((event, index) => {
            const active = event.observed && event.evidence_id === activeId;
            return (
              <li key={`${event.evidence_id || "marker"}-${index}`} data-kind={event.kind} data-active={active}>
                <time dateTime={event.timestamp || undefined}>{formatTimestamp(event.timestamp)}</time>
                <span className="rail" aria-hidden="true" />
                <div className="event-body">
                  <p className="kind">{KIND_LABEL[event.kind]}</p>
                  <p>{event.description}</p>
                  <p className="event-meta">
                    {event.service ? <span>{event.service}</span> : null}
                    {event.evidence_id ? (
                      <button type="button" className="text-button mono" onClick={() => onSelect(event.evidence_id)}>
                        {event.evidence_id}
                      </button>
                    ) : (
                      <span>No evidence id</span>
                    )}
                  </p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
