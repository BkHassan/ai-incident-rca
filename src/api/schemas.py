"""HTTP schemas for the investigation API.

The response body is the RCA model from ``investigation.models``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class InvestigateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_id: str = Field(pattern=r"^INC-\d{3}$")


class ErrorResponse(BaseModel):
    error: str
    detail: str
