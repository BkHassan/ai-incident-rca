"""Incident investigation route. The handler only calls InvestigationService."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from investigation import InvestigationService, RCAResult

from ..schemas import InvestigateRequest

router = APIRouter()


def get_service(request: Request) -> InvestigationService:
    service = getattr(request.app.state, "service", None)
    if service is not None:
        return service
    from investigation import build_default_service

    service = build_default_service(load_env=request.app.state.load_env)
    request.app.state.service = service
    return service


@router.post("/api/incidents/investigate", response_model=RCAResult)
def investigate_incident(
    body: InvestigateRequest,
    service: InvestigationService = Depends(get_service),
) -> RCAResult:
    return service.investigate(body.incident_id)
