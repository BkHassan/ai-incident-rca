"""Incident investigation route. The handler only calls InvestigationService."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from investigation import InvestigationService, RCAResult

from ..catalog import list_catalog, read_catalog_incident
from ..schemas import IncidentDetail, IncidentListResponse, InvestigateRequest

router = APIRouter()


def get_service(request: Request) -> InvestigationService:
    service = getattr(request.app.state, "service", None)
    if service is not None:
        return service
    from investigation import build_default_service

    service = build_default_service(load_env=request.app.state.load_env)
    request.app.state.service = service
    return service


@router.get("/api/incidents", response_model=IncidentListResponse)
def list_incidents(request: Request) -> IncidentListResponse:
    return list_catalog(request.app.state.data_dir)


@router.get("/api/incidents/{incident_id}", response_model=IncidentDetail)
def read_incident(
    incident_id: Annotated[str, Path(pattern=r"^INC-\d{3}$")],
    request: Request,
) -> IncidentDetail:
    return read_catalog_incident(incident_id, request.app.state.data_dir)


@router.post("/api/incidents/investigate", response_model=RCAResult)
def investigate_incident(
    body: InvestigateRequest,
    service: InvestigationService = Depends(get_service),
) -> RCAResult:
    return service.investigate(body.incident_id)
