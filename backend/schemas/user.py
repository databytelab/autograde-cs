"""Request/response shapes for users and authentication."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from backend.models.user import UserRole
from backend.utils.auth_utils import MAX_PASSWORD_BYTES, MIN_PASSWORD_LENGTH


class UserBase(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)


class UserCreate(UserBase):
    # bcrypt ignores bytes past 72, so the ceiling is enforced here too -
    # a rejected registration is better than a silently truncated password.
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_BYTES,
        description=f"{MIN_PASSWORD_LENGTH}-{MAX_PASSWORD_BYTES} characters",
    )
    role: UserRole = UserRole.professor


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut
