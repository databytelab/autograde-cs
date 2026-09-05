"""
CanvasCredential - one instructor's own Canvas access token.

Canvas has to be per-instructor, not per-server. A department instance has
several professors, each owning different Canvas courses, and a Canvas
token acts *as the person who created it*: one shared token cannot write
grades into another professor's course, and asking colleagues to hand over
their personal token would be a much larger ask than their files.

Stored exactly like a provider key (see provider_credential.py): the token
is encrypted with Fernet, only the last four characters are kept for
recognition, and there is no path that returns it to a browser.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, LargeBinary, String, Text,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class CanvasCredential(Base):
    __tablename__ = "canvas_credentials"

    id            = Column(String(36), primary_key=True,
                           default=lambda: str(uuid.uuid4()))
    # One per instructor - a person has one Canvas identity.
    user_id       = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                           nullable=False, unique=True, index=True)

    base_url      = Column(String(500), nullable=False)
    encrypted_token = Column(LargeBinary, nullable=False)
    token_hint    = Column(String(8), nullable=True)

    # Who Canvas says this token belongs to, filled in by the connection
    # test. Shown back to the instructor so they can confirm they pasted
    # the token they meant to.
    canvas_user_name = Column(String(255), nullable=True)

    last_tested_at   = Column(DateTime, nullable=True)
    last_test_ok     = Column(Boolean, nullable=True)
    last_test_detail = Column(Text, nullable=True)

    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    user = relationship("User")

    @property
    def masked_token(self) -> str:
        return f"****{self.token_hint}" if self.token_hint else "****"

    def __repr__(self) -> str:
        return f"<CanvasCredential {self.base_url} for {self.user_id[:8]}>"
