"""
Settings -> AI Providers.

Lets a professor grade with their own API key instead of the
administrator's. Every route here is scoped to the caller: there is no
endpoint that takes a user id, so one professor cannot read, test, or
delete another's credentials even by guessing.

No route ever returns a stored key. The response carries `masked_key`
("****ab12") and nothing else, and there is deliberately no "reveal"
endpoint - a key that is forgotten is replaced, not recovered.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.provider_credential import (
    SUPPORTED_PROVIDERS, ProviderCredential,
)
from backend.models.user import User
from backend.services import credential_service
from backend.services.credential_service import CredentialError
from backend.utils.auth_utils import get_current_user

router = APIRouter(prefix="/api/settings/providers", tags=["provider settings"])


# ---------------------------------------------------------------------
# Shapes
# ---------------------------------------------------------------------
class CredentialOut(BaseModel):
    provider: str
    masked_key: str = ""
    has_key: bool = False
    base_url: str | None = None
    model: str | None = None
    last_tested_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_detail: str | None = None


class ProviderSettingsOut(BaseModel):
    """Everything the Settings page needs in one request."""
    supported: list[str]
    credentials: list[CredentialOut]
    # None means "use the administrator's provider".
    preferred_provider: str | None = None
    using_administrator: bool = True
    administrator_provider: str
    administrator_available: bool


class CredentialIn(BaseModel):
    provider: str
    # Omit to keep the stored key; send "" to clear it.
    api_key: str | None = Field(default=None)
    base_url: str | None = None
    model: str | None = None


class PreferenceIn(BaseModel):
    # None / "administrator" both mean the shared account.
    provider: str | None = None


def _to_out(credential: ProviderCredential) -> CredentialOut:
    return CredentialOut(
        provider=credential.provider,
        masked_key=credential.masked_key,
        has_key=bool(credential.encrypted_key),
        base_url=credential.base_url,
        model=credential.model,
        last_tested_at=credential.last_tested_at,
        last_test_ok=credential.last_test_ok,
        last_test_detail=credential.last_test_detail,
    )


def _settings_payload(db: Session, user: User) -> ProviderSettingsOut:
    return ProviderSettingsOut(
        supported=list(SUPPORTED_PROVIDERS),
        credentials=[_to_out(c) for c in
                     credential_service.list_credentials(db, user)],
        preferred_provider=user.preferred_provider,
        using_administrator=not user.preferred_provider,
        administrator_provider=settings.active_provider(),
        administrator_available=settings.grading_configured(),
    )


# ---------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------
@router.get("", response_model=ProviderSettingsOut)
def get_provider_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProviderSettingsOut:
    """This professor's provider setup. Keys are masked, never returned."""
    return _settings_payload(db, current_user)


@router.put("", response_model=ProviderSettingsOut)
def save_provider_credential(
    payload: CredentialIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProviderSettingsOut:
    """
    Add or replace this professor's credential for one provider.

    Saving does not switch grading over to it - that is a separate,
    deliberate choice via PUT /preference, so pasting a key cannot silently
    redirect a running course's spend.
    """
    try:
        credential_service.save_credential(
            db, current_user, payload.provider,
            api_key=payload.api_key, base_url=payload.base_url,
            model=payload.model,
        )
    except CredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _settings_payload(db, current_user)


@router.delete("/{provider}", response_model=ProviderSettingsOut)
def delete_provider_credential(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProviderSettingsOut:
    """Remove a saved key. If it was in use, grading reverts to the admin's."""
    if not credential_service.delete_credential(db, current_user, provider):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No saved credentials for '{provider}'.",
        )
    return _settings_payload(db, current_user)


@router.post("/{provider}/test", response_model=CredentialOut)
def test_provider_credential(
    provider: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CredentialOut:
    """
    Make one small real call with the saved credential.

    Worth doing before a batch: a wrong key, an unreachable Ollama host or a
    model name that was never pulled all fail identically at grading time,
    and this turns that into an immediate, readable answer.
    """
    try:
        credential = credential_service.test_credential(db, current_user, provider)
    except CredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _to_out(credential)


@router.put("/preference", response_model=ProviderSettingsOut)
def set_provider_preference(
    payload: PreferenceIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ProviderSettingsOut:
    """Switch between the administrator's account and your own key."""
    wanted = payload.provider
    if wanted in ("", "administrator", "admin", "default"):
        wanted = None
    try:
        credential_service.set_preference(db, current_user, wanted)
    except CredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _settings_payload(db, current_user)


@router.get("/local/discover")
def discover_local(
    base_url: str | None = None,
    _user: User = Depends(get_current_user),
) -> dict:
    """
    Ask an Ollama server which models it has.

    Answers the question that trips people up first: the server AutoGrade
    would reach is not necessarily the one on the professor's laptop. What
    comes back here is what *this deployment* can see.
    """
    return credential_service.discover_local_models(base_url)


# ---------------------------------------------------------------------
# Settings -> Canvas (one connection per instructor)
# ---------------------------------------------------------------------
canvas_router = APIRouter(prefix="/api/settings/canvas", tags=["canvas settings"])


class CanvasSettingsOut(BaseModel):
    connected: bool = False
    base_url: str | None = None
    masked_token: str = ""
    canvas_user_name: str | None = None
    last_tested_at: datetime | None = None
    last_test_ok: bool | None = None
    last_test_detail: str | None = None
    # True when the server has a shared connection in .env, which a
    # single-instructor install uses instead of a personal one.
    server_fallback_available: bool = False


class CanvasSettingsIn(BaseModel):
    base_url: str
    # Omit to keep the stored token while correcting the URL.
    api_token: str | None = None


def _canvas_out(credential, ) -> CanvasSettingsOut:
    fallback = bool(settings.canvas_base_url and settings.canvas_api_token)
    if credential is None:
        return CanvasSettingsOut(server_fallback_available=fallback)
    return CanvasSettingsOut(
        connected=True,
        base_url=credential.base_url,
        masked_token=credential.masked_token,
        canvas_user_name=credential.canvas_user_name,
        last_tested_at=credential.last_tested_at,
        last_test_ok=credential.last_test_ok,
        last_test_detail=credential.last_test_detail,
        server_fallback_available=fallback,
    )


@canvas_router.get("", response_model=CanvasSettingsOut)
def get_canvas_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CanvasSettingsOut:
    """This instructor's Canvas connection. The token is never returned."""
    return _canvas_out(credential_service.get_canvas_credential(db, current_user))


@canvas_router.put("", response_model=CanvasSettingsOut)
def save_canvas_settings(
    payload: CanvasSettingsIn,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CanvasSettingsOut:
    """
    Connect Canvas, or correct the URL.

    A Canvas token acts as the person who created it, so it belongs to the
    instructor and not to the server: on a shared instance one token cannot
    write grades into somebody else's course.
    """
    try:
        credential = credential_service.save_canvas_credential(
            db, current_user, base_url=payload.base_url,
            api_token=payload.api_token,
        )
    except CredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return _canvas_out(credential)


@canvas_router.post("/test", response_model=CanvasSettingsOut)
def test_canvas_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CanvasSettingsOut:
    """
    Ask Canvas who this token belongs to.

    Returns the account name, so a token pasted from the wrong login is
    obvious before any grades are pushed anywhere.
    """
    try:
        credential = credential_service.test_canvas_credential(db, current_user)
    except CredentialError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc
    return _canvas_out(credential)


@canvas_router.delete("", response_model=CanvasSettingsOut)
def delete_canvas_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CanvasSettingsOut:
    """Disconnect Canvas. Grades already pushed are unaffected."""
    if not credential_service.delete_canvas_credential(db, current_user):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Canvas connection saved.",
        )
    return _canvas_out(None)
