"""FastAPI application for one investigation endpoint.

Run from the repository root:

    uvicorn api.main:app --app-dir src
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from investigation import InvestigationError, InvestigationService

from .routes import router

_STATUS = {
    "not_found": 404,
    "configuration_error": 503,
    "vector_store_missing": 503,
    "retrieval_failed": 502,
    "investigation_failed": 502,
    "invalid_rca": 502,
}


def create_app(service: InvestigationService | None = None, *, load_env: bool = True) -> FastAPI:
    app = FastAPI(title="Incident RCA", version="0.1.0")
    app.state.service = service
    app.state.load_env = load_env
    app.include_router(router)

    @app.exception_handler(InvestigationError)
    def _investigation_error(_request: Request, exc: InvestigationError) -> JSONResponse:
        status = _STATUS.get(exc.code, 500)
        return JSONResponse(status_code=status, content={"error": exc.code, "detail": exc.detail})

    return app


app = create_app()
