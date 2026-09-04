"""Request/response shapes for grading jobs."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class GradingJobOut(BaseModel):
    """
    A job's public state.

    Deliberately small: the Streamlit UI polls this every couple of seconds
    while a batch runs, so it must stay cheap to serialise. The per-student
    breakdown in `results` is only populated once the run has finished.
    """
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    status: str
    total: int = 0
    processed: int = 0
    graded: int = 0
    failed: int = 0
    skipped: int = 0
    progress_percent: int = 0
    attempts: int = 0
    max_attempts: int = 3
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class GradingJobDetail(GradingJobOut):
    """Adds the per-submission outcomes, for the page shown after a run."""
    results: list[dict[str, Any]] | None = None
    params: dict[str, Any] = Field(default_factory=dict)
