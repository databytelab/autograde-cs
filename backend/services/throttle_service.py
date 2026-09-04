"""
Login throttling.

Kept in the database rather than in process memory. An in-memory counter is
wrong the moment the API runs more than one uvicorn worker - each keeps its
own tally, so the effective limit is the configured one multiplied by the
worker count - and it resets on restart, which is exactly when an attacker
would like it to.

Two independent limits, because they stop different attacks:

* **per account** - stops someone grinding one professor's password;
* **per client address** - stops someone spraying one common password across
  many accounts, which the per-account limit would never see.

Failures are counted in a rolling window, and a success clears the account's
failures so a professor who mistypes twice and then gets it right is not
locked out on their next visit.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.models.login_attempt import LoginAttempt
from backend.utils.logging_utils import hash_identifier, log_event

WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_EMAIL = 8
MAX_FAILURES_PER_IP = 30

# Attempts older than this are useless for throttling and are deleted as we
# go, so the table cannot grow without bound.
RETENTION = timedelta(days=7)


class TooManyAttemptsError(RuntimeError):
    """Raised when a caller has exceeded the login rate limit."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__(
            "Too many failed sign-in attempts. Try again in a few minutes."
        )
        self.retry_after_seconds = retry_after_seconds


def _since() -> datetime:
    return datetime.utcnow() - WINDOW


def check_login_allowed(db: Session, email: str, ip_address: str | None) -> None:
    """Raise TooManyAttemptsError if this email or address is over the limit."""
    email = (email or "").lower().strip()
    since = _since()

    by_email = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.email == email,
                LoginAttempt.successful.is_(False),
                LoginAttempt.attempted_at >= since)
        .count()
    )
    if by_email >= MAX_FAILURES_PER_EMAIL:
        log_event("auth.throttled", level="warning", scope="email",
                  email_hash=hash_identifier(email), failures=by_email)
        raise TooManyAttemptsError(int(WINDOW.total_seconds()))

    if ip_address:
        by_ip = (
            db.query(LoginAttempt)
            .filter(LoginAttempt.ip_address == ip_address,
                    LoginAttempt.successful.is_(False),
                    LoginAttempt.attempted_at >= since)
            .count()
        )
        if by_ip >= MAX_FAILURES_PER_IP:
            log_event("auth.throttled", level="warning", scope="ip",
                      ip=ip_address, failures=by_ip)
            raise TooManyAttemptsError(int(WINDOW.total_seconds()))


def record_attempt(db: Session, email: str, ip_address: str | None,
                   successful: bool) -> None:
    """
    Record the outcome of a sign-in.

    Recorded even when the account does not exist, so that guessing which
    addresses are registered is throttled just like guessing passwords.
    """
    email = (email or "").lower().strip()
    db.add(LoginAttempt(email=email, ip_address=ip_address,
                        successful=successful))

    if successful:
        # A correct password clears the slate for that account.
        db.query(LoginAttempt).filter(
            LoginAttempt.email == email,
            LoginAttempt.successful.is_(False),
        ).delete(synchronize_session=False)

    db.query(LoginAttempt).filter(
        LoginAttempt.attempted_at < datetime.utcnow() - RETENTION
    ).delete(synchronize_session=False)
    db.commit()

    log_event(
        "auth.login_succeeded" if successful else "auth.login_failed",
        level="info" if successful else "warning",
        email_hash=hash_identifier(email), ip=ip_address,
    )
