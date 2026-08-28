"""
SimilarityFlag model.
Created when two submissions in the same assignment
exceed the similarity threshold.
Professor reviews and marks each flag as resolved.
"""
import uuid
from datetime import datetime
from sqlalchemy import (Column, String, DateTime, ForeignKey,
                        Numeric, Boolean, Text)
from sqlalchemy.orm import relationship
from backend.database import Base

class SimilarityFlag(Base):
    __tablename__ = "similarity_flags"

    id               = Column(String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))
    assignment_id    = Column(String(36), ForeignKey("assignments.id",
                               ondelete="CASCADE"), nullable=False, index=True)
    submission_a_id  = Column(String(36), ForeignKey("submissions.id",
                               ondelete="CASCADE"), nullable=False)
    submission_b_id  = Column(String(36), ForeignKey("submissions.id",
                               ondelete="CASCADE"), nullable=False)
    # 0.0 = completely different, 1.0 = identical
    similarity_score = Column(Numeric(4, 3), nullable=False)
    # low / moderate / high
    severity         = Column(String(20), nullable=False, default="moderate")
    # Which method detected this
    # ast_structure / token / combined
    method           = Column(String(50), nullable=False, default="combined")
    # Professor review
    reviewed         = Column(Boolean, default=False, nullable=False)
    professor_note   = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    assignment   = relationship("Assignment", back_populates="similarity_flags")
    submission_a = relationship("Submission", foreign_keys=[submission_a_id],
                                back_populates="flags_as_a")
    submission_b = relationship("Submission", foreign_keys=[submission_b_id],
                                back_populates="flags_as_b")

    def __repr__(self):
        return (f"<SimilarityFlag {self.similarity_score:.0%} — "
                f"{self.severity}>")
