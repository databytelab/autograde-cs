"""
Course model — e.g. "CS 231N Computer Vision Fall 2025"
One professor owns many courses.
One course has many assignments.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from backend.database import Base

class Course(Base):
    __tablename__ = "courses"

    id               = Column(String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))
    user_id          = Column(String(36), ForeignKey("users.id",
                               ondelete="CASCADE"), nullable=False, index=True)
    name             = Column(String(255), nullable=False)
    # e.g. "Fall 2025"
    term             = Column(String(100), nullable=True)
    # Canvas course ID for LMS integration (Stage 11)
    canvas_course_id = Column(String(100), nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at       = Column(DateTime, default=datetime.utcnow,
                               onupdate=datetime.utcnow, nullable=False)

    # Relationships
    owner       = relationship("User", back_populates="courses")
    assignments = relationship("Assignment", back_populates="course",
                               cascade="all, delete-orphan")

    @property
    def assignment_count(self) -> int:
        return len(self.assignments)

    def __repr__(self):
        return f"<Course {self.name} ({self.term})>"
