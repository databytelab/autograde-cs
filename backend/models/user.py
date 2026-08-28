"""
User model — professors and teaching assistants.
Only professors can finalize grades.
TAs can grade but not approve.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from backend.database import Base
import enum

class UserRole(str, enum.Enum):
    professor = "professor"
    ta        = "ta"

class User(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True,
                           default=lambda: str(uuid.uuid4()))
    email         = Column(String(255), unique=True, nullable=False, index=True)
    name          = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role          = Column(Enum(UserRole), default=UserRole.professor, nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # Relationships
    courses = relationship("Course", back_populates="owner",
                           cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
