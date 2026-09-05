"""Registration, login, and the current-user endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.user import User
from backend.schemas.user import (
    AdminPasswordReset, AdminUserCreate, PasswordChange, Token,
    UserCreate, UserLogin, UserOut,
)
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

    # The first account on a fresh install is always allowed and becomes the
    # administrator - otherwise a newly installed instance could never be
    # set up. After that, open registration is a deliberate choice: on a
    # shipped instance anyone who can reach the sign-in page would otherwise
    # be able to create themselves an account.
    is_first_account = db.query(User).count() == 0
    if not is_first_account and not settings.registration_is_open():
        log_event("auth.registration_refused", email_hash=hash_identifier(email))
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This AutoGrade instance does not allow self sign-up. "
                   "Ask your administrator to create an account for you.",
        )

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
        is_admin=is_first_account,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event("auth.registered", user_id=user.id, is_admin=user.is_admin,
              first_account=is_first_account)
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


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Guard the account-management endpoints."""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This action requires the administrator account.",
        )
    return current_user


@router.get("/registration-status")
def registration_status(db: Session = Depends(get_db)) -> dict:
    """
    Whether the sign-in page should offer "Create an account".

    Unauthenticated on purpose: the page needs it before anyone is signed
    in. It reveals only whether sign-up is open and whether this instance
    has been set up yet - not who is on it.
    """
    return {
        "open": settings.registration_is_open(),
        "needs_first_account": db.query(User).count() == 0,
    }


@router.post("/change-password", response_model=UserOut)
def change_password(
    payload: PasswordChange,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserOut:
    """
    Change your own password.

    The current password is required, so a borrowed session cannot be used
    to lock the real owner out.
    """
    if not verify_password(payload.current_password, current_user.password_hash):
        log_event("auth.password_change_failed", user_id=current_user.id,
                  level="warning")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Your current password is not correct.",
        )
    try:
        current_user.password_hash = hash_password(payload.new_password)
    except PasswordTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    log_event("auth.password_changed", user_id=current_user.id)
    return UserOut.model_validate(current_user)


@router.get("/users", response_model=list[UserOut])
def list_users(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> list[UserOut]:
    """Every account on this instance. Administrator only."""
    return [UserOut.model_validate(u)
            for u in db.query(User).order_by(User.created_at).all()]


@router.post("/users", response_model=UserOut,
             status_code=status.HTTP_201_CREATED)
def create_user(
    payload: AdminUserCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserOut:
    """
    Create an account for a colleague.

    This is how accounts are made on an instance with self sign-up closed,
    which is the recommended setting once the instance is in use.
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

    user = User(email=email, name=payload.name.strip(),
                password_hash=password_hash, role=payload.role)
    db.add(user)
    db.commit()
    db.refresh(user)
    log_event("auth.user_created_by_admin", user_id=user.id,
              created_by=admin.id)
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/reset-password", response_model=UserOut)
def reset_password(
    user_id: str,
    payload: AdminPasswordReset,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserOut:
    """
    Set a new password for someone who is locked out.

    There is no email-based self-service reset; on a self-hosted instance
    with no mail server, an administrator doing this is the honest answer.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No such account.")
    try:
        user.password_hash = hash_password(payload.new_password)
    except PasswordTooLongError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    db.commit()
    log_event("auth.password_reset_by_admin", user_id=user.id,
              reset_by=admin.id, level="warning")
    return UserOut.model_validate(user)


@router.post("/users/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
) -> UserOut:
    """
    Disable an account without deleting anything it owns.

    Deleting a user would cascade to their courses and grades; a colleague
    who leaves should lose access, not take the gradebook with them.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own administrator account.",
        )
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="No such account.")
    user.is_active = False
    db.commit()
    log_event("auth.user_deactivated", user_id=user.id, by=admin.id,
              level="warning")
    return UserOut.model_validate(user)
