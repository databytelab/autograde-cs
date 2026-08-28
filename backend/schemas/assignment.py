"""Request/response shapes for assignments and rubrics."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RubricLevel(BaseModel):
    label: str
    points: float = Field(ge=0)
    description: str = ""


class RubricCriterion(BaseModel):
    id: str | None = None
    name: str = Field(min_length=1)
    description: str = ""
    max_points: float = Field(ge=0)
    weight: float = Field(default=1.0, gt=0)
    levels: list[RubricLevel] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    requires_output: bool = False


class Rubric(BaseModel):
    """
    The canonical rubric shape. Mirrors backend/services/rubric_service.py -
    that module remains the authority; this exists so the API documents
    and rejects malformed rubrics before they reach it.
    """
    title: str = "Untitled rubric"
    total_points: float | None = None
    criteria: list[RubricCriterion] = Field(min_length=1)
    grading_notes: str = ""
    warnings: list[str] = Field(default_factory=list)


class AssignmentBase(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    total_possible_points: float = Field(default=100.0, gt=0)
    due_date: datetime | None = None
    canvas_assignment_id: str | None = Field(default=None, max_length=100)


class AssignmentCreate(AssignmentBase):
    """
    Supply the rubric one of three ways:
      * `rubric_json`      - already-structured rubric
      * `rubric_raw_text`  - prose, which Claude turns into a rubric
      * neither            - a default CS rubric is generated
    """
    course_id: str
    rubric_json: dict[str, Any] | None = None
    rubric_raw_text: str | None = None

    @model_validator(mode="after")
    def _only_one_rubric_source(self) -> "AssignmentCreate":
        if self.rubric_json and self.rubric_raw_text:
            raise ValueError(
                "Provide either rubric_json or rubric_raw_text, not both."
            )
        return self


class AssignmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    total_possible_points: float | None = Field(default=None, gt=0)
    due_date: datetime | None = None
    status: str | None = None
    canvas_assignment_id: str | None = None
    rubric_json: dict[str, Any] | None = None


class AssignmentOut(AssignmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    course_id: str
    status: str
    rubric_json: dict[str, Any] | None = None
    rubric_raw_text: str | None = None
    expected_submission_path: str | None = None
    created_at: datetime
    updated_at: datetime
    submission_count: int = 0
    graded_count: int = 0


class RubricPreviewRequest(BaseModel):
    """Turn prose into a rubric without saving anything."""
    text: str = Field(min_length=10)
    total_points: float | None = Field(default=None, gt=0)
