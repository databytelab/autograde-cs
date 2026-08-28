"""
Submission model — one row per student file uploaded.
Tracks parse status, grading status, and stores the
parsed notebook content as JSON for reuse.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Integer, Text
from sqlalchemy.orm import relationship
from backend.database import Base

class SubmissionStatus(str):
    PENDING  = "pending"    # uploaded, not yet parsed
    PARSING  = "parsing"    # being parsed
    GRADING  = "grading"    # AI grading in progress
    GRADED   = "graded"     # grade result created
    ERROR    = "error"      # parse or grading failure
    FLAGGED  = "flagged"    # similarity or integrity flag

class Submission(Base):
    __tablename__ = "submissions"

    id                  = Column(String(36), primary_key=True,
                                 default=lambda: str(uuid.uuid4()))
    assignment_id       = Column(String(36), ForeignKey("assignments.id",
                                 ondelete="CASCADE"), nullable=False, index=True)
    # Student identity — filled from filename or Canvas roster
    student_name        = Column(String(255), nullable=True)
    student_email       = Column(String(255), nullable=True)
    # External ID from Canvas (used when pushing grades back)
    student_id_external = Column(String(100), nullable=True)
    # File storage
    original_filename   = Column(String(500), nullable=False)
    file_path           = Column(String(500), nullable=False)
    # ipynb / html / py
    file_type           = Column(String(20), nullable=False)
    file_size_bytes     = Column(Integer, nullable=True)
    # Cached output of the parser — avoids re-parsing on regrade
    parsed_content      = Column(JSON, nullable=True)
    # Workflow status
    status              = Column(String(50), default="pending", nullable=False)
    error_message       = Column(Text, nullable=True)
    submitted_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    graded_at           = Column(DateTime, nullable=True)

    # Relationships
    assignment   = relationship("Assignment", back_populates="submissions")
    grade_result = relationship("GradeResult", back_populates="submission",
                                uselist=False, cascade="all, delete-orphan")
    # This submission can appear in similarity flags as either side
    flags_as_a   = relationship("SimilarityFlag",
                                foreign_keys="SimilarityFlag.submission_a_id",
                                back_populates="submission_a")
    flags_as_b   = relationship("SimilarityFlag",
                                foreign_keys="SimilarityFlag.submission_b_id",
                                back_populates="submission_b")

    def __repr__(self):
        return f"<Submission {self.student_name} — {self.file_type}>"
