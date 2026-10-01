import { formatTimestamp } from "@/lib/format";
import type { IncidentHeaderModel } from "@/lib/types";

export function IncidentHeader({ header, demo }: { header: IncidentHeaderModel; demo: boolean }) {
  return (
    <header className="incident-header" data-testid="incident-header">
      <p className="kicker">Incident investigation</p>
      <h1>
        Incident <span className="mono">{header.incident_id}</span>
      </h1>
      <p className="incident-title">{header.title}</p>
      <dl className="meta">
        <div>
          <dt>Severity</dt>
          <dd>
            <span className={`severity severity-${header.severity.toLowerCase()}`}>{header.severity}</span>
          </dd>
        </div>
        <div>
          <dt>Alerting service</dt>
          <dd>{header.services.length ? header.services.join(", ") : "Not included in the RCA response"}</dd>
        </div>
        <div>
          <dt>Status</dt>
          <dd>{header.status}</dd>
        </div>
        <div>
          <dt>Start time</dt>
          <dd className="mono">{formatTimestamp(header.start_time)}</dd>
        </div>
      </dl>
      {demo ? (
        <p className="demo-banner" role="note">
          Demo fixture. This is not a live Gemini investigation.
        </p>
      ) : null}
    </header>
  );
}
