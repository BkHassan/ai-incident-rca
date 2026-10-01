"""Errors raised when raw dataset files cannot be ingested."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

MAX_ISSUES_IN_MESSAGE = 10


@dataclass(frozen=True)
class RecordIssue:
    """One problem found in a file, e.g. a malformed log line or metric row."""

    location: str  # "line 12", "row 7", "file", "field 'severity'"
    reason: str
    incident_id: str | None = None

    def __str__(self) -> str:
        where = f"{self.location} [{self.incident_id}]" if self.incident_id else self.location
        return f"{where}: {self.reason}"


class IngestionError(ValueError):
    """A raw file failed parsing or validation.

    ``issues`` lists every problem found in the file, so one run reports all malformed
    records instead of only the first.
    """

    def __init__(self, path: str | Path, issues: list[RecordIssue], incident_id: str | None = None):
        self.path = Path(path)
        self.issues = tuple(issues)
        self.incident_id = incident_id
        super().__init__(self._format())

    def _format(self) -> str:
        head = f"{self.path}: {len(self.issues)} problem(s)"
        if self.incident_id:
            head += f" in incident {self.incident_id}"
        lines = [head] + [f"  - {issue}" for issue in self.issues[:MAX_ISSUES_IN_MESSAGE]]
        if len(self.issues) > MAX_ISSUES_IN_MESSAGE:
            lines.append(f"  - ... {len(self.issues) - MAX_ISSUES_IN_MESSAGE} more")
        return "\n".join(lines)


def describe_validation_error(exc: ValidationError) -> str:
    """Condense a Pydantic ValidationError into one line: ``field: message; field: message``."""
    parts = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "record"
        parts.append(f"{field}: {error['msg']}")
    return "; ".join(parts)
