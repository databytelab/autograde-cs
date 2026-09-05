"""
ProviderCredential - one professor's own API key for one provider.

"Bring your own key": a professor can grade with the administrator's shared
account, or with their own OpenAI / Anthropic / local-model credentials.

What is stored, and what deliberately is not:

* `encrypted_key` holds the key encrypted with Fernet (AES-128-CBC +
  HMAC-SHA256). The plaintext is never written to the database, never
  returned by the API, and never logged.
* `key_hint` is the last four characters only - enough for a professor to
  recognise which key they saved, useless to anyone who reads the table.
* There is no "decrypt for display" path anywhere. A key that is forgotten
  is replaced, not recovered. That is the point.

One row per (user, provider), so a professor can keep an OpenAI key and an
Ollama endpoint side by side and switch between them. Which one is actually
used is `User.preferred_provider`; NULL there means "use the administrator's
configured provider".
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, LargeBinary, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from backend.database import Base

# The providers a professor may configure for themselves. Matches the
# factory in backend/ai/providers/__init__.py - BYOK adds no new grading
# path, it only supplies different credentials to the existing one.
SUPPORTED_PROVIDERS = ("openai", "anthropic", "local")


class ProviderCredential(Base):
    __tablename__ = "provider_credentials"

    id            = Column(String(36), primary_key=True,
                           default=lambda: str(uuid.uuid4()))
    user_id       = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"),
                           nullable=False, index=True)
    provider      = Column(String(30), nullable=False)

    # Fernet ciphertext. Bytes, not text: it is not meant to be read.
    encrypted_key = Column(LargeBinary, nullable=True)
    # Last four characters of the plaintext, for "which key is this?".
    key_hint      = Column(String(8), nullable=True)

    # For `local` (Ollama/vLLM/LM Studio) and OpenAI-compatible gateways.
    base_url      = Column(String(500), nullable=True)
    # Optional per-professor model override; falls back to the server default.
    model         = Column(String(120), nullable=True)

    # Result of the last "Test" the professor ran, so the UI can show whether
    # the credential is known-good without testing on every page load.
    last_tested_at   = Column(DateTime, nullable=True)
    last_test_ok     = Column(Boolean, nullable=True)
    last_test_detail = Column(Text, nullable=True)

    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_provider_credential"),
    )

    @property
    def masked_key(self) -> str:
        """What the UI shows. Never the key itself."""
        if not self.encrypted_key:
            return ""
        return f"****{self.key_hint}" if self.key_hint else "****"

    def __repr__(self) -> str:
        return f"<ProviderCredential {self.provider} for {self.user_id[:8]}>"
