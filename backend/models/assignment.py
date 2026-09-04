"""
Assignment model.
Holds the rubric JSON and optional path to the instructor solution notebook.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Numeric, Text
from sqlalchemy.orm import relationship
from backend.database import Base
from backend.models.submission import SubmissionStatus

class AssignmentStatus(str):
    PENDING  = "pending"    # created, no submissions yet
    GRADING  = "grading"    # grading in progress
    COMPLETE = "complete"   # all submissions graded
    ARCHIVED = "archived"   # past semester, read-only

class Assignment(Base):
    __tablename__ = "assignments"

    id                       = Column(String(36), primary_key=True,
                                      default=lambda: str(uuid.uuid4()))
    course_id                = Column(String(36), ForeignKey("courses.id",
                                      ondelete="CASCADE"), nullable=False, index=True)
    name                     = Column(String(255), nullable=False)
    description              = Column(Text, nullable=True)
    # Full rubric stored as JSON — see docs/rubric_format.md for schema
    rubric_json              = Column(JSON, nullable=True)
    # Raw text rubric before parsing (preserved for re-parsing)
    rubric_raw_text          = Column(Text, nullable=True)
    # Filesystem path to instructor solution .ipynb (optional)
    expected_submission_path = Column(String(500), nullable=True)
    total_possible_points    = Column(Numeric(6, 2), default=100.0, nullable=False)
    status                   = Column(String(50), default="pending", nullable=False)
    # Canvas assignment ID for grade push-back (Stage 11)
    canvas_assignment_id     = Column(String(100), nullable=True)
    due_date                 = Column(DateTime, nullable=True)
    created_at               = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at               = Column(DateTime, default=datetime.utcnow,
                                      onupdate=datetime.utcnow, nullable=False)

    # Relationships
    course          = relationship("Course", back_populates="assignments")
    submissions     = relationship("Submission", back_populates="assignment",
                                   cascade="all, delete-orphan")
    similarity_flags = relationship("SimilarityFlag", back_populates="assignment",
                                    cascade="all, delete-orphan")

    @property
    def submission_count(self) -> int:
        return len(self.submissions)

    @property
    def graded_count(self) -> int:
        # "flagged" is a *graded* submission that carries an integrity or
        # quality flag, so it counts here. Excluding it made this disagree
        # with assignment_stats (which counts submissions that have a grade)
        # and under-reported progress on exactly the submissions a professor
        # most needs to look at.
        return sum(
            1 for s in self.submissions
            if s.status in (SubmissionStatus.GRADED, SubmissionStatus.FLAGGED)
        )

    def __repr__(self):
        return f"<Assignment {self.name}>"
