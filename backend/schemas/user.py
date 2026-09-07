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

    # A plain string on the way out, deliberately, even though `UserBase`
    # validates it strictly on the way in.
    #
    # Re-validating a value we already stored turns one odd row into a 500
    # for the whole endpoint. It did: an account seeded long ago with a
    # `.local` address - a reserved TLD that email-validator refuses -
    # made GET /api/auth/users fail entirely, so an administrator could not
    # see or manage *any* account. Input validation is where an address is
    # judged; output is where it is reported.
    email: str

    id: str

    is_admin: bool = False
    role: UserRole
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: UserOut


class PasswordChange(BaseModel):
    """Change your own password. The current one is required."""
    current_password: str
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_BYTES)


class AdminUserCreate(BaseModel):
    """An administrator creating an account for a colleague."""
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_BYTES)
    role: UserRole = UserRole.professor


class AdminPasswordReset(BaseModel):
    """An administrator setting a new password for someone who is locked out."""
    new_password: str = Field(min_length=MIN_PASSWORD_LENGTH, max_length=MAX_PASSWORD_BYTES)
