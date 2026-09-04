"""Registration, login, and the current-user endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.user import User
from backend.schemas.user import Token, UserCreate, UserLogin, UserOut
from backend.services.throttle_service import (
    TooManyAttemptsError,
    check_login_allowed,
    record_attempt,
)
from backend.utils.auth_utils import (
    PasswordTooLongError,
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from backend.utils.logging_utils import hash_identifier, log_event

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


def _client_ip(request: Request) -> str | None:
    """
    The caller's address, honouring the reverse proxy.

    Only the first hop of X-Forwarded-For is used, and only because this
    service is deployed behind a proxy that sets it. Do not expose the API
    directly to the internet, or the header becomes attacker-controlled and
    the per-address limit becomes trivially evadable.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.client.host[:64] if request.client else None


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
) -> Token:
    """
    Log in with email and password.

    Uses the OAuth2 password form so the Swagger "Authorize" button works;
    the `username` field carries the email address.

    Rate-limited per account and per client address - see throttle_service.
    """
    email = form.username.lower().strip()
    ip_address = _client_ip(request)

    try:
        check_login_allowed(db, email, ip_address)
    except TooManyAttemptsError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
            headers={"Retry-After": str(exc.retry_after_seconds)},
        ) from exc

    user = db.query(User).filter(User.email == email).first()

    # Same message and same code path for both failures - a different
    # response for "no such user" would let anyone enumerate accounts.
    if user is None or not verify_password(form.password, user.password_hash):
        record_attempt(db, email, ip_address, successful=False)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        # Not counted as a failed password: the credentials were right.
        log_event("auth.login_deactivated", level="warning",
                  email_hash=hash_identifier(email), ip=ip_address)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This account has been deactivated",
        )

    record_attempt(db, email, ip_address, successful=True)
    return _issue_token(user)


@router.post("/login-json", response_model=Token)
def login_json(request: Request, payload: UserLogin,
               db: Session = Depends(get_db)) -> Token:
    """JSON-body login, for clients that would rather not post a form."""
    form = OAuth2PasswordRequestForm(
        username=payload.email, password=payload.password, scope=""
    )
    return login(request=request, form=form, db=db)


@router.get("/me", response_model=UserOut)
def me(current_user: User = Depends(get_current_user)) -> UserOut:
    """The account behind the current token."""
    return UserOut.model_validate(current_user)
