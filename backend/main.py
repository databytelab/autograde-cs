"""
AutoGrade CS - FastAPI Application Entry Point

Run with:
    uvicorn backend.main:app --reload
Then open http://localhost:8000/docs
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.ai.grader import GradingError
from backend.config import settings
from backend.parsers.base import ParseError
from backend.routers import (
    assignments, auth, courses, export, results, settings_providers, submissions,
)
from backend.services.rubric_service import RubricError
from backend.utils.file_utils import FileTooLargeError, UnsupportedFileError, upload_root
from backend.utils.logging_utils import configure_logging, log_event

configure_logging()
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup checks. Surfaces a missing API key before a professor
    uploads 200 notebooks and only then discovers grading is offline, and
    refuses to boot a production deployment on development defaults."""
    for warning in settings.assert_production_ready():
        logger.warning("Deployment warning: %s", warning)
    upload_root()
    log_event(
        "app.started",
        env=settings.environment,
        database=settings.database_url.split("://", 1)[0],
        provider=settings.active_provider(),
        grading="ready" if settings.grading_configured() else "not_configured",
    )
    yield


app = FastAPI(
    title="AutoGrade CS",
    lifespan=lifespan,
    description=(
        "AI-powered assignment grading for CS courses.\n\n"
        "Upload student `.ipynb` / `.html` / `.py` files, grade them against "
        "a rubric with Claude, review and override the results, then export "
        "to CSV, Excel, PDF, or Canvas."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Defence-in-depth headers. The reverse proxy sets these too; setting them
# here as well means they are still present if the API is ever reached
# directly (a port-forward while debugging, say) and it keeps the policy
# next to the app it describes rather than only in deployment config.
_SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    # This is a JSON API - it should never be a source of active content.
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in _SECURITY_HEADERS.items():
        response.headers.setdefault(header, value)
    if settings.is_production():
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )
    return response


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    """
    Reject an over-sized request before it is read.

    The upload path already streams with a per-file cap, but that only
    protects the upload route. This is the blanket limit that stops a large
    body reaching any endpoint - the proxy enforces the same number, this is
    the backstop if the API is reached directly.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit():
        if int(declared) > settings.max_request_body_mb * 1024 * 1024:
            log_event("http.body_too_large", level="warning",
                      path=request.url.path, bytes=int(declared))
            return JSONResponse(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                content={"detail":
                         f"Request body exceeds the "
                         f"{settings.max_request_body_mb} MB limit."},
            )
    return await call_next(request)


# ---------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------
# These turn our domain exceptions into clean API responses wherever they
# escape a route, so no service module has to import FastAPI to report a
# problem properly.
@app.exception_handler(ParseError)
async def _parse_error(_request: Request, exc: ParseError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": f"Could not parse the submission: {exc}"},
    )


@app.exception_handler(RubricError)
async def _rubric_error(_request: Request, exc: RubricError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": str(exc)},
    )


@app.exception_handler(GradingError)
async def _grading_error(_request: Request, exc: GradingError) -> JSONResponse:
    # 503: the request was fine, the grading backend was not.
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": str(exc)},
    )


@app.exception_handler(UnsupportedFileError)
async def _unsupported_file(_request: Request, exc: UnsupportedFileError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        content={"detail": str(exc)},
    )


@app.exception_handler(FileTooLargeError)
async def _file_too_large(_request: Request, exc: FileTooLargeError) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
        content={"detail": str(exc)},
    )


@app.exception_handler(RequestValidationError)
async def _validation_error(
    _request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Flatten Pydantic's nested error list into something readable."""
    problems = [
        {
            "field": ".".join(str(p) for p in err["loc"][1:]) or err["loc"][0],
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Request validation failed", "problems": problems},
    )


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(courses.router)
app.include_router(assignments.router)
app.include_router(submissions.router)
app.include_router(results.router)
app.include_router(export.router)
app.include_router(settings_providers.router)
app.include_router(settings_providers.canvas_router)


@app.get("/api/health", tags=["health"])
async def health(response: Response) -> dict:
    """
    Liveness plus a readiness summary.

    The database is actually queried rather than assumed. A container whose
    schema has never been migrated used to report healthy while every real
    request returned 500, so an orchestrator happily routed traffic to a
    backend that could not serve any of it.

    `llm_configured` being false means everything works except grading -
    which is worth surfacing before a professor uploads 200 notebooks.
    `llm_provider` says which backend (openai / anthropic / local) will run.
    `anthropic_configured` is kept for backward compatibility.
    """
    from sqlalchemy import text

    from backend.database import SessionLocal
    from backend.services.canvas_service import is_configured as canvas_configured

    database_ok = True
    try:
        with SessionLocal() as session:
            session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001 - any failure means "do not send traffic"
        logger.exception("Health check could not reach the database")
        database_ok = False
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    key = settings.anthropic_api_key
    return {
        "status": "ok" if database_ok else "degraded",
        "version": "1.0.0",
        "environment": settings.environment,
        "database_ok": database_ok,
        "llm_provider": settings.active_provider(),
        "llm_configured": settings.grading_configured(),
        "anthropic_configured": bool(key and not key.startswith("your_")),
        "canvas_configured": canvas_configured(),
    }
