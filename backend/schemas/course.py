"""Request/response shapes for courses."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CourseBase(BaseModel):
    name: str = Field(min_length=1, max_length=255,
                      examples=["CS 231N Computer Vision"])
    term: str | None = Field(default=None, max_length=100, examples=["Fall 2025"])
    canvas_course_id: str | None = Field(default=None, max_length=100)


class CourseCreate(CourseBase):
    pass


class CourseUpdate(BaseModel):
    """Every field optional - this is a PATCH body."""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    term: str | None = Field(default=None, max_length=100)
    canvas_course_id: str | None = Field(default=None, max_length=100)


class CourseOut(CourseBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime
    assignment_count: int = 0
