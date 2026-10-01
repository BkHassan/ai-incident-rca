"""FastAPI application for one investigation endpoint.

Run from the repository root:

    uvicorn api.main:app --app-dir src
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ingestion import DEFAULT_DATA_DIR
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


def create_app(
    service: InvestigationService | None = None,
    *,
    load_env: bool = True,
    data_dir: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Incident RCA", version="0.1.0")
    app.state.service = service
    app.state.load_env = load_env
    app.state.data_dir = Path(data_dir) if data_dir is not None else DEFAULT_DATA_DIR
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(127\.0\.0\.1|localhost):\d+",
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(router)

    @app.exception_handler(InvestigationError)
    def _investigation_error(_request: Request, exc: InvestigationError) -> JSONResponse:
        status = _STATUS.get(exc.code, 500)
        return JSONResponse(status_code=status, content={"error": exc.code, "detail": exc.detail})

    return app


app = create_app()
