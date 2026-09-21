"""Request/response shapes for grade results and professor overrides."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CriterionResult(BaseModel):
    criterion_id: str
    name: str
    score: float
    max_score: float
    reasoning: str = ""
    feedback: str = ""
    flags: list[str] = Field(default_factory=list)


class GradeResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    submission_id: str
    total_score: float | None = None
    total_possible: float | None = None
    percentage: float | None = None
    letter_grade: str | None = None
    criteria_results: list[CriterionResult] | None = None
    flags: list[str] = Field(default_factory=list)
    professor_overrides: dict[str, Any] | None = None
    # A hand-entered final score. When present it is the score, and the
    # per-criterion numbers are audit trail only. None means the score is
    # computed from the criteria.
    total_override: float | None = None
    summary_feedback: str | None = None
    finalized: bool = False
    finalized_at: datetime | None = None
    created_at: datetime
    updated_at: datetime

    # Computed on the model, not stored - the score after overrides.
    effective_score: float | None = None


class GradeResultDetail(GradeResultOut):
    """Adds the untouched model output. Audit view only."""
    ai_raw_output: dict[str, Any] | None = None
    student_name: str | None = None
    original_filename: str | None = None


class CriterionOverride(BaseModel):
    new_score: float = Field(ge=0)
    note: str = ""


class OverrideRequest(BaseModel):
    """
    Adjust one or more criterion scores.

    Overrides are stored beside the AI scores rather than replacing them,
    so the original judgement stays auditable. Keys are criterion ids.
    """
    overrides: dict[str, CriterionOverride] = Field(min_length=1)
    summary_feedback: str | None = Field(
        default=None,
        description="Replace the AI's summary paragraph. Omit to keep it.",
    )


class TotalOverrideRequest(BaseModel):
    """
    Set a submission's final score directly, out of its total_possible.

    `value` is None to clear the manual total and revert to the
    criterion-based score. The bound is checked server-side against the
    rubric total, so a value over the maximum is rejected there.
    """
    value: float | None = Field(
        default=None,
        description="The final score, or null to clear the manual total.",
    )


class FinalizeRequest(BaseModel):
    finalized: bool = True


class AssignmentStats(BaseModel):
    """Dashboard numbers for one assignment."""
    assignment_id: str
    assignment_name: str
    total_submissions: int
    graded: int
    pending: int
    errored: int
    finalized: int
    flagged: int
    mean_percentage: float | None = None
    median_percentage: float | None = None
    min_percentage: float | None = None
    max_percentage: float | None = None
    grade_distribution: dict[str, int] = Field(default_factory=dict)
