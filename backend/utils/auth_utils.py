"""
Password hashing and JWT issuing/verification.

We call `bcrypt` directly rather than going through passlib. passlib
1.7.x reads `bcrypt.__about__.__version__`, which bcrypt 4+ removed, so
the combination raises at hash time. Talking to bcrypt directly is one
fewer dependency and one fewer version trap.

bcrypt silently ignores anything past the 72nd byte of a password, which
would make two different long passwords interchangeable. We reject
over-length passwords instead of truncating them.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.user import User, UserRole

# bcrypt's hard limit. Enforced, not worked around.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8

# tokenUrl is what Swagger UI's "Authorize" button posts to.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login")


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds bcrypt's 72-byte ceiling."""


# ---------------------------------------------------------------------
# Passwords
# ---------------------------------------------------------------------
def hash_password(password: str) -> str:
    """Hash a plaintext password. Returns the full bcrypt string."""
    encoded = password.encode("utf-8")
    if len(encoded) > MAX_PASSWORD_BYTES:
        raise PasswordTooLongError(
            f"Password must be at most {MAX_PASSWORD_BYTES} bytes "
            f"({len(encoded)} given)."
        )
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """
    Check a plaintext password against a stored hash.

    Returns False rather than raising for malformed hashes, so a corrupt
    row cannot turn a failed login into a 500.
    """
    try:
        encoded = password.encode("utf-8")
        if len(encoded) > MAX_PASSWORD_BYTES:
            return False
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------
# Tokens
# ---------------------------------------------------------------------
def create_access_token(
    subject: str,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Issue a signed JWT.

    `subject` is the user id. Claims are kept minimal on purpose - the
    token is a pointer to a database row, not a copy of it.
    """
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """
    Decode and verify a JWT.

    Raises HTTPException(401) for anything wrong with the token, so
    callers never have to distinguish expiry from tampering.
    """
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


# ---------------------------------------------------------------------
# FastAPI dependencies
# ---------------------------------------------------------------------
def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the bearer token to a live, active User row."""
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing a subject",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated",
        )
    return user


def require_professor(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    Guard endpoints that only a professor may call.

    TAs can grade and leave notes; only a professor can finalize a grade
    or delete a course.
    """
    if current_user.role != UserRole.professor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the professor role",
        )
    return current_user
