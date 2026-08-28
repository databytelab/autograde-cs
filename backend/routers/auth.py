"""Registration, login, and the current-user endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.user import User
from backend.schemas.user import Token, UserCreate, UserLogin, UserOut
from backend.utils.auth_utils import (
    PasswordTooLongError,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _issue_token(user: User) -> Token:
    token = create_access_token(user.id, {"role": user.role.value})
    return Token(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        user=UserOut.model_validate(user),
    )


@router.post("/register", response_model=Token,
             status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, db: Session = Depends(get_db)) -> Token:
    """
    Create an account and return a token.

    Email is the unique key. We check for a duplicate up front to return
    a clear 409 rather than an opaque integrity error.
    """
    email = payload.email.lower().strip()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        )

    try:
        password_hash = hash_password(payload.password)
    except PasswordTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    user = User(
        email=email,
        name=payload.name.strip(),
        password_hash=password_hash,
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return _issue_token(user)


@router.post("/login", response_model=Token)
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """
    Log in with email and password.

    Uses the OAuth2 password form so the Swagger "Authorize" button works;
    the `username` field carries the email address.
    """
    user = db.query(User).filter(User.email == form.username.lower().strip()).first()

    # Same message and same code path for both failures - a different
    # response for "no such user" would let anyone enumerate accounts.
    if user is None or not verify_password(form.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated",
        )

    return _issue_token(user)


@router.post("/login-json", response_model=Token)
def login_json(payload: UserLogin, db: Session = Depends(get_db)) -> Token:
    """JSON-body login, for clients that would rather not post a form."""
    form = OAuth2PasswordRequestForm(
        username=payload.email, password=payload.password, scope=""
    )
    return login(form=form, db=db)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """The account behind the current token."""
    return UserOut.model_validate(current_user)
