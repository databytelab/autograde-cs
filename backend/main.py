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
from backend.routers import assignments, auth, courses, export, results, submissions
from backend.services.rubric_service import RubricError
from backend.utils.file_utils import FileTooLargeError, UnsupportedFileError, upload_root

logging.basicConfig(
    level=logging.INFO if settings.environment == "development" else logging.WARNING,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup checks. Surfaces a missing API key before a professor
    uploads 200 notebooks and only then discovers grading is offline, and
    refuses to boot a production deployment on development defaults."""
    for warning in settings.assert_production_ready():
        logger.warning("Deployment warning: %s", warning)
    upload_root()
    logger.info(
        "AutoGrade CS started (env=%s, db=%s, llm_provider=%s, grading=%s)",
        settings.environment,
        settings.database_url.split("://", 1)[0],
        settings.active_provider(),
        "ready" if settings.grading_configured() else "NOT CONFIGURED",
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
    allow_origins=["http://localhost:3000", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
