"""
GradeResult model — AI-generated grade for one submission.
Stores both the raw AI output and any professor overrides
separately, so we can always diff what changed.
"""
import uuid
from datetime import datetime
from sqlalchemy import (Column, String, DateTime, ForeignKey,
                        JSON, Numeric, Boolean, Text)
from sqlalchemy.orm import relationship
from backend.database import Base

class GradeResult(Base):
    __tablename__ = "grade_results"

    id                 = Column(String(36), primary_key=True,
                                default=lambda: str(uuid.uuid4()))
    # One-to-one with Submission
    submission_id      = Column(String(36), ForeignKey("submissions.id",
                                ondelete="CASCADE"), unique=True,
                                nullable=False, index=True)
    # Scores
    total_score        = Column(Numeric(6, 2), nullable=True)
    total_possible     = Column(Numeric(6, 2), nullable=True)
    percentage         = Column(Numeric(5, 2), nullable=True)
    letter_grade       = Column(String(5), nullable=True)
    # Per-criterion breakdown from AI
    # Schema: [{"criterion_id", "name", "score", "max_score",
    #           "reasoning", "feedback", "flags"}, ...]
    criteria_results   = Column(JSON, nullable=True)
    # Flags raised during grading
    # e.g. ["possible_ai_generated", "no_outputs", "below_accuracy_threshold"]
    flags              = Column(JSON, default=list, nullable=False)
    # Exact raw output from Claude — never modified, preserved for audit
    ai_raw_output      = Column(JSON, nullable=True)
    # Professor's manual overrides
    # Schema: {"criterion_id": {"new_score": x, "note": "..."}, ...}
    professor_overrides = Column(JSON, nullable=True)
    # A final score entered by hand, bypassing the per-criterion breakdown.
    # When set it wins over the criteria (see effective_score); NULL means
    # "compute from the criteria as usual". Used for submissions graded
    # manually - e.g. one whose HTML converted badly - where the professor
    # wants to enter one number, not fill in every section.
    total_override     = Column(Numeric(6, 2), nullable=True)
    # Overall feedback paragraph shown to student
    summary_feedback   = Column(Text, nullable=True)
    # Whether professor has approved this grade
    finalized          = Column(Boolean, default=False, nullable=False)
    finalized_at       = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at         = Column(DateTime, default=datetime.utcnow,
                                onupdate=datetime.utcnow, nullable=False)

    # Relationships
    submission = relationship("Submission", back_populates="grade_result")

    @property
    def effective_score(self) -> float:
        """
        Returns the final score after applying professor overrides.
        If no overrides exist, returns the AI-generated total.

        A hand-entered `total_override` wins over everything: when the
        professor has set a final score directly, that is the score, and
        the per-criterion numbers - AI or overridden - are kept only for
        the audit trail.
        """
        if self.total_override is not None:
            return float(self.total_override)
        if not self.professor_overrides or not self.criteria_results:
            return float(self.total_score or 0)
        # Recalculate from per-criterion scores + overrides
        total = 0.0
        for criterion in self.criteria_results:
            cid = criterion["criterion_id"]
            override = self.professor_overrides.get(cid)
            if override and "new_score" in override:
                total += float(override["new_score"])
            else:
                total += float(criterion["score"])
        return total

    def __repr__(self):
        return f"<GradeResult {self.total_score}/{self.total_possible}>"
