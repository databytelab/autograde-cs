"""Request/response shapes for submissions and similarity flags."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SubmissionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    student_name: str | None = None
    student_email: str | None = None
    student_id_external: str | None = None
    original_filename: str
    file_type: str
    file_size_bytes: int | None = None
    status: str
    error_message: str | None = None
    submitted_at: datetime
    graded_at: datetime | None = None


class SubmissionDetail(SubmissionOut):
    """Adds the cached parse result - large, so it is not in list responses."""
    parsed_content: dict[str, Any] | None = None


class SubmissionUpdate(BaseModel):
    """Correct the student identity the filename guessed wrong."""
    student_name: str | None = Field(default=None, max_length=255)
    student_email: str | None = Field(default=None, max_length=255)
    student_id_external: str | None = Field(default=None, max_length=100)


class UploadResult(BaseModel):
    """Per-file outcome of a bulk upload - failures never abort the batch."""
    filename: str
    ok: bool
    submission_id: str | None = None
    student_name: str | None = None
    error: str | None = None


class UploadResponse(BaseModel):
    assignment_id: str
    uploaded: int
    failed: int
    results: list[UploadResult]


class GradeRequest(BaseModel):
    """Kick off grading for an assignment."""
    submission_ids: list[str] | None = Field(
        default=None,
        description="Grade only these submissions. Omit to grade every "
                    "ungraded submission in the assignment.",
    )
    regrade: bool = Field(
        default=False,
        description="Re-grade submissions that already have a result.",
    )
    include_images: bool = True


class GradeJobResult(BaseModel):
    submission_id: str
    student_name: str | None = None
    ok: bool
    total_score: float | None = None
    percentage: float | None = None
    letter_grade: str | None = None
    flags: list[str] = Field(default_factory=list)
    error: str | None = None


class GradeResponse(BaseModel):
    assignment_id: str
    graded: int
    failed: int
    skipped: int
    results: list[GradeJobResult]


class SimilarityFlagOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    assignment_id: str
    submission_a_id: str
    submission_b_id: str
    similarity_score: float
    severity: str
    method: str
    reviewed: bool
    professor_note: str | None = None
    created_at: datetime


class SimilarityFlagDetail(SimilarityFlagOut):
    """Adds the student names so the professor knows who to talk to."""
    student_a_name: str | None = None
    student_b_name: str | None = None


class SimilarityScanRequest(BaseModel):
    threshold: float = Field(
        default=0.5, ge=0.0, le=1.0,
        description="Minimum combined similarity to record a flag.",
    )
    clear_existing: bool = Field(
        default=True,
        description="Delete previous unreviewed flags before scanning.",
    )


class SimilarityReviewRequest(BaseModel):
    reviewed: bool = True
    professor_note: str | None = None
