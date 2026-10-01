"use client";

import { useState } from "react";
import { Section } from "@/components/ui/Section";
import { Body, Meta } from "@/components/ui/Type";
import {
  formatDuration,
  formatTimestamp,
  type AnomalyMetricSummary,
  type AnomalyWindow,
  type TimelineEvidence,
} from "@/lib/incidents";
import { categoryLabel, timelineCategory, timelineRows, type TimelineCategory } from "@/lib/timeline";

export function AnomalySummary({
  metrics,
  windows,
}: {
  metrics: AnomalyMetricSummary[];
  windows: AnomalyWindow[];
}) {
  if (metrics.length === 0 && windows.length === 0) return null;
  return (
    <Section id="anomalies-detected" title="Anomalies detected">
      <Meta>Only metrics with detections on this incident. Counts are aggregates. A window is a cluster of points, not a cause.</Meta>
      {metrics.length > 0 ? (
        <ul className="metric-summary">
          {metrics.map((metric) => (
            <li key={metric.metric}>
              <span className="metric-name">{metric.label}</span>
              <span className="meta">
                {metric.point_count} points · {metric.window_count}{" "}
                {metric.window_count === 1 ? "window" : "windows"}
                {metric.peak_severity ? ` · peak ${metric.peak_severity}` : ""}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <Body>No metric summary is available.</Body>
      )}
      {windows.length > 0 ? (
        <ul className="window-list">
          {windows.map((window) => (
            <li key={`${window.start_time}-${window.peak_service}-${window.peak_metric}`}>
              <span className="mark mark-window" aria-hidden="true" />
              <span>
                {formatTimestamp(window.start_time)} – {formatTimestamp(window.end_time)} ·{" "}
                {formatDuration(window.duration_minutes)} · {window.anomaly_count} points · {window.peak_service}:
                {window.peak_metric}
                {window.peak_z_score === null ? "" : ` · z ${window.peak_z_score}`} · {window.severity}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </Section>
  );
}

export function EvidenceTimeline({
  start,
  end,
  items,
  available,
}: {
  start: string;
  end: string;
  items: TimelineEvidence[];
  available: boolean;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  if (!available) {
    return (
      <Section id="evidence-timeline" title="What happened before and during this incident">
        <Body>No derived timeline is available for this incident.</Body>
      </Section>
    );
  }
  const rows = timelineRows(start, end, items);
  const selected = items.find((item) => item.evidence_id === selectedId) ?? null;
  const hasChange = items.some((item) => timelineCategory(item) === "change");
  return (
    <Section id="evidence-timeline" title="What happened before and during this incident">
      <Meta>
        Records above the alert start were already present. Records between the boundaries are during the alert.
        These are correlated records, not every raw log or metric minute. Order is not causation.
      </Meta>
      {hasChange ? null : <Meta>No deployment, restart, or configuration records were correlated for this incident.</Meta>}
      <div className="timeline-layout">
        <ol className="otime">
          {rows.map((row) =>
            row.kind === "boundary" ? (
              <li key={row.id} className="otime-row">
                <span className="mark mark-boundary" aria-hidden="true" />
                <div>
                  <span className="type-label">{categoryLabel.boundary}</span>
                  <span className="meta">{formatTimestamp(row.timestamp)}</span>
                  <span>{row.label}</span>
                </div>
              </li>
            ) : (
              <li key={row.item.evidence_id} className="otime-row">
                <EvidenceButton item={row.item} pressed={selectedId === row.item.evidence_id} onSelect={setSelectedId} />
              </li>
            ),
          )}
        </ol>
        <EvidenceContext item={selected} items={items} onSelect={setSelectedId} onClose={() => setSelectedId(null)} />
      </div>
    </Section>
  );
}

function EvidenceButton({
  item,
  pressed,
  onSelect,
}: {
  item: TimelineEvidence;
  pressed: boolean;
  onSelect: (id: string) => void;
}) {
  const category = timelineCategory(item);
  return (
    <>
      <span className={`mark mark-${category}`} aria-hidden="true" />
      <button type="button" className="otime-hit" aria-pressed={pressed} onClick={() => onSelect(item.evidence_id)}>
        <span className="type-label">{categoryLabel[category]}</span>
        <span className="mono">{item.evidence_id}</span>
        <span className="meta">
          {formatTimestamp(item.timestamp)} · {item.service}
          {item.occurrence_count && item.occurrence_count > 1 ? ` · ${item.occurrence_count} occurrences` : ""}
        </span>
        <span>{item.summary || item.title}</span>
      </button>
    </>
  );
}

function EvidenceContext({
  item,
  items,
  onSelect,
  onClose,
}: {
  item: TimelineEvidence | null;
  items: TimelineEvidence[];
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  if (!item) {
    return (
      <aside className="evidence-context" aria-live="polite">
        <Meta>Select a record to see its evidence id, type, and the summary stored with it.</Meta>
      </aside>
    );
  }
  const category: TimelineCategory = timelineCategory(item);
  const known = new Set(items.map((entry) => entry.evidence_id));
  return (
    <aside className="evidence-context" aria-live="polite">
      <p className="type-label">{categoryLabel[category]}</p>
      <p className="mono">{item.evidence_id}</p>
      <p>{item.summary || item.title}</p>
      <dl className="meta-list">
        <div>
          <dt>Time</dt>
          <dd>{formatTimestamp(item.timestamp)}</dd>
        </div>
        <div>
          <dt>Service</dt>
          <dd>{item.service}</dd>
        </div>
        <div>
          <dt>Type</dt>
          <dd>{item.evidence_type || item.source_type}</dd>
        </div>
        {item.metric_name ? (
          <div>
            <dt>Metric</dt>
            <dd>{item.metric_name}</dd>
          </div>
        ) : null}
        {item.event_type ? (
          <div>
            <dt>Event</dt>
            <dd>{item.event_type}</dd>
          </div>
        ) : null}
        {item.severity ? (
          <div>
            <dt>Severity</dt>
            <dd>{item.severity}</dd>
          </div>
        ) : null}
        <div>
          <dt>Occurrences</dt>
          <dd>{item.occurrence_count ?? 1}</dd>
        </div>
        {item.last_timestamp ? (
          <div>
            <dt>Last seen</dt>
            <dd>{formatTimestamp(item.last_timestamp)}</dd>
          </div>
        ) : null}
      </dl>
      {item.related_evidence_ids && item.related_evidence_ids.length > 0 ? (
        <div>
          <Meta>Related evidence</Meta>
          <ul className="plain-list">
            {item.related_evidence_ids.map((id) => (
              <li key={id}>
                {known.has(id) ? (
                  <button type="button" className="text-button" onClick={() => onSelect(id)}>
                    {id}
                  </button>
                ) : (
                  <span className="mono">{id}</span>
                )}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <button type="button" className="text-button" onClick={onClose}>
        Close
      </button>
    </aside>
  );
}
