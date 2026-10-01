"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { SeverityBadge } from "@/components/incidents/SeverityBadge";
import { EmptyState } from "@/components/ui/Section";
import { Body, Meta } from "@/components/ui/Type";
import {
  filterIncidents,
  formatDuration,
  formatTimestamp,
  severitiesIn,
  uniqueSorted,
  type IncidentSummary,
} from "@/lib/incidents";
import { hrefWithIncident } from "@/lib/product";

export function IncidentList({ incidents }: { incidents: IncidentSummary[] }) {
  const [query, setQuery] = useState("");
  const [service, setService] = useState("");
  const [severity, setSeverity] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const services = useMemo(() => uniqueSorted(incidents.map((incident) => incident.service)), [incidents]);
  const severities = useMemo(() => severitiesIn(incidents), [incidents]);
  const shown = useMemo(
    () => filterIncidents(incidents, query, service, severity),
    [incidents, query, service, severity],
  );
  const preview = shown.find((incident) => incident.incident_id === previewId) ?? null;

  return (
    <div className="explorer-layout">
      <div className="stack">
        <form className="filters" role="search" onSubmit={(event) => event.preventDefault()}>
          <label>
            Search
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Id, title, service, or description"
            />
          </label>
          <label>
            Alerting service
            <select value={service} onChange={(event) => setService(event.target.value)}>
              <option value="">All services</option>
              {services.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Alert severity
            <select value={severity} onChange={(event) => setSeverity(event.target.value)}>
              <option value="">All severities</option>
              {severities.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </form>
        <Meta>
          {shown.length} of {incidents.length} shown
        </Meta>
        {shown.length === 0 ? (
          <EmptyState title="No incidents match">
            Change the search or filters. The catalog itself is unchanged.
          </EmptyState>
        ) : (
          <ul className="incident-list">
            {shown.map((incident) => (
              <li key={incident.incident_id}>
                <Link
                  className="incident-row"
                  href={`/incidents/${incident.incident_id}`}
                  data-preview={preview?.incident_id === incident.incident_id ? "true" : undefined}
                  onMouseEnter={() => setPreviewId(incident.incident_id)}
                  onFocus={() => setPreviewId(incident.incident_id)}
                >
                  <span className="mono row-id">{incident.incident_id}</span>
                  <span className="row-main">
                    <span className="row-title">{incident.title}</span>
                    <span className="meta">
                      {incident.service} · {formatDuration(incident.duration_minutes)}
                    </span>
                  </span>
                  <SeverityBadge severity={incident.severity} />
                  <span className="meta row-time">
                    {formatTimestamp(incident.start_time)} – {formatTimestamp(incident.end_time)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
      <aside className="preview" aria-label="Incident preview">
        {preview ? <IncidentPreview incident={preview} /> : (
          <EmptyState title="No preview">
            Focus or hover an incident. Open it for logs, metric series, and the observational timeline.
          </EmptyState>
        )}
      </aside>
    </div>
  );
}

function IncidentPreview({ incident }: { incident: IncidentSummary }) {
  return (
    <div className="stack">
      <p className="kicker">Alert metadata</p>
      <p className="mono">{incident.incident_id}</p>
      <p className="row-title">{incident.title}</p>
      <SeverityBadge severity={incident.severity} />
      <Body>{incident.description}</Body>
      <dl className="meta-list">
        <div>
          <dt>Alerting service</dt>
          <dd>{incident.service}</dd>
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
      </dl>
      <Meta>The alerting service is where the alert fired. It is not a proven cause.</Meta>
      <div className="action-row">
        <Link className="primary-action" href={hrefWithIncident("/investigations", incident.incident_id)}>
          Investigate incident
        </Link>
        <Link className="text-link" href={`/incidents/${incident.incident_id}`}>
          Open incident
        </Link>
      </div>
    </div>
  );
}
