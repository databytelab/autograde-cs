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
    # Which grading credentials this professor uses.
    #   NULL          -> the administrator's server-wide provider (the default)
    #   "openai" etc. -> this professor's own key, from provider_credentials
    # Kept on the user rather than inferred from which keys exist, so adding
    # a second key does not silently change which one grades.
    preferred_provider = Column(String(30), nullable=True)
    # The first account created on a fresh install. Can create accounts and
    # reset passwords - the minimum needed to run an instance without
    # anyone reaching for a database client.
    is_admin      = Column(Boolean, default=False, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # Relationships
    courses = relationship("Course", back_populates="owner",
                           cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
