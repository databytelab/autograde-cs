"""
LoginAttempt - the record behind login throttling.

Kept in the database rather than in process memory on purpose. An in-memory
counter is wrong as soon as the API runs more than one uvicorn worker (each
would keep its own tally, multiplying the real limit by the worker count)
and it forgets everything on restart, which is exactly when an attacker
would like it to.

Only what throttling needs is stored: the email that was tried, the client
address, and when. No password material, ever - not even a hash of one.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Index, String

from backend.database import Base


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id           = Column(String(36), primary_key=True,
                          default=lambda: str(uuid.uuid4()))
    # Lower-cased email as supplied. Recorded even when no such account
    # exists, so guessing usernames is throttled too.
    email        = Column(String(255), nullable=False)
    ip_address   = Column(String(64), nullable=True)
    successful   = Column(Boolean, default=False, nullable=False)
    attempted_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("ix_login_attempts_email_time", "email", "attempted_at"),
        Index("ix_login_attempts_ip_time", "ip_address", "attempted_at"),
    )

    def __repr__(self) -> str:
        return f"<LoginAttempt {self.email} ok={self.successful}>"
