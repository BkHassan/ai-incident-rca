import Link from "next/link";
import { AnomalySummary, EvidenceTimeline } from "@/components/incidents/EvidenceTimeline";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";
import { Section } from "@/components/ui/Section";
import { Body, Kicker, Meta, PageTitle } from "@/components/ui/Type";
import { formatDuration, formatTimestamp, type IncidentDetail } from "@/lib/incidents";
import { investigationHref } from "@/lib/product";

export function IncidentDetailView({ incident }: { incident: IncidentDetail }) {
  return (
    <div className="stack explorer">
      <header className="page-head">
        <Kicker>Alert metadata</Kicker>
        <p className="mono">{incident.incident_id}</p>
        <PageTitle>{incident.title}</PageTitle>
        <SeverityBadge severity={incident.severity} />
        <Body>{incident.description}</Body>
      </header>
      <Section id="incident-metadata" title="Metadata">
        <dl className="meta-list">
          <div>
            <dt>Alerting service</dt>
            <dd>{incident.service}</dd>
          </div>
          <div>
            <dt>Alert severity</dt>
            <dd>{incident.severity}</dd>
          </div>
          <div>
            <dt>Start</dt>
            <dd>{formatTimestamp(incident.start_time)}</dd>
          </div>
          <div>
            <dt>End</dt>
            <dd>{formatTimestamp(incident.end_time)}</dd>
          </div>
          <div>
            <dt>Duration</dt>
            <dd>{formatDuration(incident.duration_minutes)}</dd>
          </div>
          <div>
            <dt>Observation window</dt>
            <dd>
              {formatTimestamp(incident.window_start)} – {formatTimestamp(incident.window_end)}
            </dd>
          </div>
        </dl>
        <Meta>The alerting service is where the alert fired. It is not a proven cause.</Meta>
      </Section>
      <div className="action-row">
        <Link className="primary-action investigate-cta" href={investigationHref(incident.incident_id)}>
          Investigate incident
        </Link>
        <Link className="text-link" href="/incidents">
          Back to catalog
        </Link>
      </div>
      <Section id="observed-logs" title="Observed logs">
        <Meta>Counts of log lines. Event types describe individual lines. They are not an incident category or a cause.</Meta>
        <p>{incident.logs.line_count} lines</p>
        <ul className="plain-list">
          {Object.entries(incident.logs.by_level).map(([level, count]) => (
            <li key={level}>
              {level} {count}
            </li>
          ))}
        </ul>
        <Meta>Services in the log file: {incident.logs.services.join(", ") || "none"}</Meta>
        <ul className="plain-list">
          {incident.logs.event_types.map((item) => (
            <li key={item.name}>
              {item.name} {item.count}
            </li>
          ))}
        </ul>
      </Section>
      <Section id="observed-metrics" title="Observed metric series">
        <Meta>
          {incident.metrics.row_count} rows. A series is listed when that service has at least one value. This is not
          a chart and not a detector result.
        </Meta>
        <ul className="plain-list">
          {incident.metrics.series.map((series) => (
            <li key={series}>{series}</li>
          ))}
        </ul>
      </Section>
      {incident.anomalies_available ? (
        <AnomalySummary metrics={incident.anomaly_metrics ?? []} windows={incident.anomaly_windows} />
      ) : (
        <Section id="anomalies-detected" title="Anomalies detected">
          <Body>No derived anomaly report is available for this incident.</Body>
        </Section>
      )}
      <EvidenceTimeline
        start={incident.start_time}
        end={incident.end_time}
        items={incident.timeline}
        available={incident.timeline_available}
      />
    </div>
  );
}
