# Temporal correlation (Day 6)

This layer reconstructs an **observed** incident timeline from Day 4 logs and Day 5 anomaly windows. It answers what was recorded, when, in what order, and which services appear in that evidence. It does not say that one record produced another.

```text
IncidentEvidenceBundle + IncidentAnomalyReport
        ↓
   time windows + relevance rules
        ↓
   EvidenceItem (LOG- / ANOM- / ANOMWIN-)
        ↓
   IncidentTimeline
```

```bash
python -m unittest tests.test_correlation
python scripts/correlate_incidents.py    # writes data/derived/correlation/INC-XXX.json
```

## What correlation may see

- `IncidentContext` alert times (`start_time`, `end_time`) and the alerting `service`
- `LogEvent` records
- `AnomalyPoint` / `AnomalyWindow` from detection

It never reads `true_root_cause`, `scenario`, `fault_start_time`, `expected_symptoms`, or `resolution`. Involved services are taken from the evidence items, not from ground-truth `affected_services`.

## Time windows (configurable)

Defaults are MVP heuristics for this 1-minute dataset:

| Window | Default | Role |
|---|---|---|
| Investigation | alert start − 30 min through alert end + 10 min, clipped to the case window | Primary log and anomaly-onset selection |
| Change lookback | alert start − 90 min | Deploy, restart, config, flags, autoscaling, scheduled jobs |
| Log-to-window link | ± 5 min around an anomaly window | Nearby logs cited on `ANOMWIN-*` via `related_evidence_ids` |

`fault_start_time` is not used. A long Day 5 window that overlaps the investigation span is kept even if it began before the 30-minute lookback; its start is the observed onset of that window.

## Relevance

A log is kept because of its own `event_type` and `level`, never because of a diagnosis:

- **Always (any level):** deploy, restart, start, autoscaling, config, feature flags, scheduled jobs, OOM, process kill, circuit breaker, host eject/restore
- **WARN/ERROR of operational types:** timeouts, request failures, db wait/error, downstream errors, retries, health-check failures, memory pressure, and similar
- **Not kept:** request completed/started, cache hits, routine db queries, INFO health checks, pool stats, GC INFO, and other high-volume chatter

High-volume types are **collapsed** to one evidence item per `(service, event_type)` with `occurrence_count` and `last_timestamp`. Rare/change logs stay one-per-occurrence.

Collapsed logs are included when they fall near an anomaly window, or in the investigation span on the alerting service or on a service already listed on an overlapping window. If there are no windows, in-span relevant logs are kept.

Metric onsets on the timeline are the **first** point of each notable series (alerting service, each window's peak series, or HIGH severity), not every anomalous minute.

## Output

Each `data/derived/correlation/INC-XXX.json` is an `IncidentTimeline`:

- `events` — chronological `TimelineEvent` rows (`title` is observational, e.g. `db timeout on payment-api x71`)
- `evidence_items` — citable `LOG-000001`, `ANOM-000001`, `ANOMWIN-000001`
- `involved_services` — services that actually appear on those items
- `first_observed_event` — earliest timeline row (not a claim of cause)
- `earliest_relevant_log` / `earliest_anomaly`
- `anomaly_windows` — overlapping Day 5 windows
- `config` used

Equal timestamps sort by source (log, then metric anomaly, then window), then service, then evidence id.

## Sanity on the 35-case dataset

- 35/35 incidents produced a timeline; none was empty.
- About 2,079 timeline events / evidence items in total (mean ~59 per incident).
- NORMAL cases: 22–49 events. Failures: 39–163. NORMAL is not huge; two failures (INC-010, INC-030) are long because a large Day 5 window overlaps many services' logs.
- Every timeline is time-ordered. Derived JSON contains no evaluation-label fields.

## Limitations

- `first_observed_event` is the earliest **relevant** record in the configured windows. Background WARN/ERROR and unrelated deploys can win that slot.
- Day 5 windows merge services, so `involved_services` often includes callers and neighbors, not only the alerting service.
- Collapsing by type hides intra-minute order of repeated errors; the first timestamp of the group is what appears on the timeline.
- Titles never use causal verbs. Quoted log text may still contain phrases such as "due to" that the application itself wrote.
