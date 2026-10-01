"""Load per-incident metric CSV files into validated ``MetricPoint`` objects.

Each row of ``raw/metrics/INC-XXX.csv`` is one service at one minute. Blank cells in
``db_connection_utilization`` and ``downstream_latency_ms`` mean "not applicable to this
service" and become ``None``. Blank cells in any other column are errors.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from pydantic import ValidationError

from .errors import IngestionError, RecordIssue, describe_validation_error
from .models import METRIC_FIELDS, NULLABLE_METRIC_FIELDS, MetricPoint

REQUIRED_COLUMNS = ("timestamp", "incident_id", "service", *METRIC_FIELDS)


def _parse_number(column: str, raw: object) -> tuple[float | None, str | None]:
    """Return ``(value, problem)`` for one cell. Parsing the text with ``float`` keeps the value exact."""
    if not isinstance(raw, str):
        return None, f"column {column!r} is missing (row has too few fields)"
    text = raw.strip()
    if not text:
        if column in NULLABLE_METRIC_FIELDS:
            return None, None
        return None, f"column {column!r} is blank but required"
    try:
        return float(text), None
    except ValueError:
        return None, f"column {column!r} value {raw!r} is not a number"


def load_metrics(path: str | Path, incident_id: str | None = None) -> list[MetricPoint]:
    """Load and validate one metrics CSV, sorted by timestamp, then service.

    If ``incident_id`` is given, every row must belong to it. Each ``(timestamp, service)`` pair
    may occur only once. All problems in the file are collected and raised together as one
    ``IngestionError``. A missing file raises ``OSError``.
    """
    path = Path(path)
    try:
        # Read every cell as text so that pandas neither converts blanks to NaN nor rounds values.
        frame = pd.read_csv(path, dtype=str, keep_default_na=False, na_filter=False, encoding="utf-8")
    except (pd.errors.ParserError, pd.errors.EmptyDataError, UnicodeDecodeError) as exc:
        raise IngestionError(path, [RecordIssue("file", f"unreadable CSV ({exc})")], incident_id) from exc

    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    unexpected = [c for c in frame.columns if c not in REQUIRED_COLUMNS]
    if missing or unexpected:
        reasons = ([f"missing columns {missing}"] if missing else []) + \
                  ([f"unexpected columns {unexpected}"] if unexpected else [])
        raise IngestionError(path, [RecordIssue("header", "; ".join(reasons))], incident_id)
    if frame.empty:
        raise IngestionError(path, [RecordIssue("file", "contains no metric rows")], incident_id)

    points: list[MetricPoint] = []
    issues: list[RecordIssue] = []
    first_seen: dict[tuple, int] = {}
    for row_no, row in enumerate(frame.to_dict("records"), start=2):  # line 1 is the header
        location = f"row {row_no}"
        rid = row["incident_id"] if isinstance(row["incident_id"], str) else None
        values: dict[str, object] = {"timestamp": row["timestamp"], "incident_id": row["incident_id"],
                                     "service": row["service"]}
        problems = []
        for column in METRIC_FIELDS:
            values[column], problem = _parse_number(column, row[column])
            if problem:
                problems.append(problem)
        if problems:
            issues.append(RecordIssue(location, "; ".join(problems), rid))
            continue
        try:
            point = MetricPoint.model_validate(values)
        except ValidationError as exc:
            issues.append(RecordIssue(location, describe_validation_error(exc), rid))
            continue
        if incident_id is not None and point.incident_id != incident_id:
            issues.append(RecordIssue(location, f"row belongs to {point.incident_id}, expected {incident_id}", rid))
            continue
        key = (point.timestamp, point.service)
        if key in first_seen:
            issues.append(RecordIssue(location, f"duplicate row for {point.service} at {point.timestamp.isoformat()} "
                                                f"(first seen in row {first_seen[key]})", rid))
            continue
        first_seen[key] = row_no
        points.append(point)
    if issues:
        raise IngestionError(path, issues, incident_id)
    return sorted(points, key=lambda point: (point.timestamp, point.service))
