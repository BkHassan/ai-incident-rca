# Statistical anomaly detection (Day 5)

This layer scores the normalized metric streams from Day 4 against a **causal rolling baseline**. It does not diagnose a root cause. It does not read logs, incident titles, or any ground-truth field.

```text
MetricPoint series  →  causal baseline  →  z-score (+ optional ceiling)  →  AnomalyPoint
                                                                        →  AnomalyWindow
```

Run it with:

```bash
python -m unittest tests.test_detection
python scripts/detect_anomalies.py          # all 35 incidents → data/derived/anomalies/
```

## What the detector is allowed to see

Only `MetricPoint` values (and, for `detect_incident`, the incident id on `IncidentEvidenceBundle`). It never imports or reads `true_root_cause`, `scenario`, `root_cause_service`, `root_cause_variant`, `root_cause_detail`, `expected_symptoms`, `fault_start_time`, or `resolution`.

Every service and every applicable metric is scored with the **same** rules. There is no per-scenario metric selection.

`None` cells (`db_connection_utilization` on api-gateway, `downstream_latency_ms` on database and recommendation-service) are skipped, not filled in.

## Causal baseline

For observation `t`, the baseline is computed from values **before** `t` only:

- **Recent window:** the last 15 accepted observations (`baseline_window=15`, `min_baseline_points=10`). Equivalent to a pandas `shift(1).rolling(15)`.
- **Lagged window** (`drift_lag=30`): 15 observations that end 30 accepted observations earlier. A slow ramp can stay inside a moving 15-minute window; the lagged window still sees the old level.

The current value is never part of its own baseline. Later values cannot change an earlier score.

During the first 9 minutes of a series there is no z-score. A point can still be flagged if it crosses an absolute ceiling.

Flagged observations are **left out of later baselines** (`exclude_anomalies_from_baseline=True`) so a sustained shift stays anomalous instead of becoming the new normal. The baseline still uses only the past.

## Scoring

```text
z = (value - mean) / max(std, min_std)
```

`min_std` is a per-metric floor so a perfectly flat series does not divide by zero.

A z-score point is flagged only if **all** of these hold:

1. `|z| >= z_threshold` (default 3.0)
2. `|value - mean|` is at least `max(min_abs_deviation, min_rel_deviation * |mean|)` (practical-significance floor)
3. the direction is allowed for that metric (default: both up and down)

A second check, **drift z-score**, uses the lagged baseline with the same rules. It exists so gradual memory growth is not absorbed by the recent window.

**Absolute ceilings** (cpu/memory/db utilization ≥ 90) can flag saturation even during warm-up. They are the same for every service and incident; they do not encode a scenario.

## Severity

These bounds are **MVP heuristics**, not an industry standard. They were set from the unlabeled `|z|` distribution on this dataset, where failure spikes often produce `|z|` of tens to hundreds because the 15-minute baseline is tight.

| `|z|` | severity |
|---|---|
| below 10 | LOW |
| 10 inclusive, below 50 | MEDIUM |
| 50 and above | HIGH |

A point flagged only by an absolute ceiling is MEDIUM.

## Windows

Anomaly points of one incident are merged across services and metrics while consecutive timestamps are at most `window_max_gap_minutes=2` minutes apart. Each window records the time span, the series involved, the count, and the strongest deviation.

## Default configuration

| Parameter | Default |
|---|---|
| `baseline_window` | 15 |
| `min_baseline_points` | 10 |
| `z_threshold` | 3.0 |
| `drift_lag` | 30 |
| `window_max_gap_minutes` | 2 |
| cpu / memory / db util | `min_abs_deviation` 10 / 5 / 10; ceiling 90 |
| latency / downstream latency | `min_abs_deviation` 20 and `min_rel_deviation` 0.5 |
| error_rate | `min_abs_deviation` 1.0 (percentage point) |
| request_rate | `min_rel_deviation` 0.3 |

Change any of these through `DetectorConfig`. Do not treat them as universal SRE thresholds.

## Derived output

`data/derived/anomalies/INC-XXX.json` is one `IncidentAnomalyReport`: detector name/version, the config used, the anomaly points, and the windows. The raw dataset is not modified.

## Sanity on the 35-case dataset (seed 42)

Detection itself does not use labels. After writing the files, `scripts/detect_anomalies.py` loads ground truth **separately** to print this check.

- 35/35 incidents produced at least one anomaly point (NORMAL cases contain designed blips).
- NORMAL: 7–39 points per case. Failures: 140–811.
- Every failure has a window that overlaps the alert period (`start_time`–`end_time`).
- Most points are `latency_ms`, then `error_rate` and `downstream_latency_ms`. That matches how this dataset expresses faults; no single metric is the whole output.
- About 11% of points are `drift_zscore` (needed for memory ramps). The rest are `rolling_zscore`.

## Limitations

- A 15-minute window on a low-variance series yields very large `|z|` when latency jumps from ~200 ms to seconds. Severity therefore uses high cut-offs.
- Excluding flagged points from the baseline keeps an entire plateau flagged. That is useful for a sustained incident and noisy if a brief blip is followed by a slightly different steady state.
- The detector does not look at logs, so a timeout that barely moves metrics can be missed.
- Metric resolution is one minute, so a one-minute spike and a one-minute gap are the finest events it can represent.
- This is not a root-cause ranker. Windows are input for later correlation, not a diagnosis.
