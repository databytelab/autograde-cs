"""
Per-professor AI provider credentials ("bring your own key").

Three ways a professor can be graded against, in priority order:

  1. Their own key for a provider they selected  (preferred_provider set)
  2. The administrator's server-wide provider     (preferred_provider NULL)

That is the whole feature. It deliberately adds no second grading path -
`resolve_provider_for_user` returns the same `LLMProvider` objects the
factory already builds, just constructed with different credentials, so
grading behaviour is identical whoever's key pays for it.

Encryption
----------
Keys are encrypted at rest with Fernet (AES-128-CBC + HMAC-SHA256). The
encryption key is derived from `CREDENTIAL_ENCRYPTION_KEY` if set, otherwise
from `SECRET_KEY` - which means **rotating SECRET_KEY makes stored provider
keys undecryptable** and every professor must re-enter theirs. Set
CREDENTIAL_ENCRYPTION_KEY explicitly if you expect to rotate the JWT secret.

A decrypted key exists only inside a grading call. It is never returned by
the API, never rendered, and `logging_utils._REDACT` drops any log field
whose name looks like a credential.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from backend.config import settings
from backend.models.provider_credential import (
    SUPPORTED_PROVIDERS, ProviderCredential,
)
from backend.models.user import User
from backend.utils.logging_utils import log_event


class CredentialError(ValueError):
    """A credential could not be saved, decrypted, or tested."""


def _fernet() -> Fernet:
    """
    Build the Fernet cipher from configuration.

    Fernet needs a url-safe base64 32-byte key; the configured secret is
    hashed to exactly that, so any passphrase length works.
    """
    secret = (settings.credential_encryption_key or settings.secret_key or "").strip()
    if not secret:
        raise CredentialError("No encryption secret configured.")
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode("utf-8"))


def _decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise CredentialError(
            "This saved key could not be decrypted. That normally means "
            "SECRET_KEY (or CREDENTIAL_ENCRYPTION_KEY) changed since it was "
            "saved. Remove the key and enter it again."
        ) from exc


# ---------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------
def list_credentials(db: Session, user: User) -> list[ProviderCredential]:
    return (
        db.query(ProviderCredential)
        .filter(ProviderCredential.user_id == user.id)
        .order_by(ProviderCredential.provider)
        .all()
    )


def get_credential(db: Session, user: User,
                   provider: str) -> ProviderCredential | None:
    return (
        db.query(ProviderCredential)
        .filter(ProviderCredential.user_id == user.id,
                ProviderCredential.provider == provider)
        .first()
    )


def save_credential(
    db: Session,
    user: User,
    provider: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> ProviderCredential:
    """
    Create or replace one professor's credential for one provider.

    `api_key=None` leaves an existing key untouched, so a professor can
    change the model or URL without re-typing their key. Passing an empty
    string is different: it clears the key.
    """
    provider = (provider or "").strip().lower()
    if provider not in SUPPORTED_PROVIDERS:
        raise CredentialError(
            f"'{provider}' is not a supported provider. "
            f"Choose one of: {', '.join(SUPPORTED_PROVIDERS)}."
        )

    # A local model server is reached by URL and needs no key; every hosted
    # provider does.
    if provider != "local" and api_key is not None and not api_key.strip():
        raise CredentialError("An API key is required for this provider.")
    if provider == "local" and not (base_url or "").strip():
        raise CredentialError(
            "A base URL is required for a local model server, "
            "for example http://localhost:11434/v1"
        )

    credential = get_credential(db, user, provider)
    if credential is None:
        credential = ProviderCredential(user_id=user.id, provider=provider)
        db.add(credential)

    if api_key is not None:
        key = api_key.strip()
        if key:
            credential.encrypted_key = _encrypt(key)
            credential.key_hint = key[-4:]
        else:
            credential.encrypted_key = None
            credential.key_hint = None
    credential.base_url = (base_url or "").strip() or None
    credential.model = (model or "").strip() or None
    credential.updated_at = datetime.utcnow()
    # A changed credential invalidates the previous test result.
    credential.last_tested_at = None
    credential.last_test_ok = None
    credential.last_test_detail = None

    db.commit()
    db.refresh(credential)
    log_event("provider_credential.saved", user_id=user.id, provider=provider,
              has_key=bool(credential.encrypted_key))
    return credential


def delete_credential(db: Session, user: User, provider: str) -> bool:
    """Remove a credential, and stop using it if it was selected."""
    credential = get_credential(db, user, provider)
    if credential is None:
        return False
    db.delete(credential)
    if user.preferred_provider == provider:
        user.preferred_provider = None
    db.commit()
    log_event("provider_credential.deleted", user_id=user.id, provider=provider)
    return True


def set_preference(db: Session, user: User, provider: str | None) -> User:
    """
    Choose whose credentials grade this professor's work.

    `None` means the administrator's server-wide provider. Anything else
    must be a provider they have actually configured, so the selection
    cannot point at a key that is not there.
    """
    if provider is not None:
        provider = provider.strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise CredentialError(f"'{provider}' is not a supported provider.")
        credential = get_credential(db, user, provider)
        if credential is None:
            raise CredentialError(
                f"You have not saved credentials for '{provider}' yet."
            )
        if provider != "local" and not credential.encrypted_key:
            raise CredentialError(
                f"Your '{provider}' entry has no API key saved."
            )
    user.preferred_provider = provider
    db.commit()
    db.refresh(user)
    log_event("provider_credential.preference_set", user_id=user.id,
              provider=provider or "administrator")
    return user


# ---------------------------------------------------------------------
# Building a provider
# ---------------------------------------------------------------------
def _provider_from(provider: str, api_key: str, base_url: str | None,
                   model: str | None):
    """Construct one of the existing providers with explicit credentials."""
    from backend.ai.providers.anthropic_provider import AnthropicProvider
    from backend.ai.providers.openai_provider import OpenAICompatibleProvider

    if provider == "anthropic":
        return AnthropicProvider(
            api_key=api_key,
            grading_model=model or settings.anthropic_grading_model,
            rubric_model=model or settings.anthropic_rubric_model,
        )
    if provider == "local":
        chosen = model or settings.local_model
        return OpenAICompatibleProvider(
            name="local", api_key=api_key or settings.local_api_key,
            base_url=base_url or settings.local_base_url,
            grading_model=chosen, rubric_model=chosen,
        )
    return OpenAICompatibleProvider(
        name="openai", api_key=api_key,
        base_url=base_url or (settings.openai_base_url or None),
        grading_model=model or settings.openai_grading_model,
        rubric_model=model or settings.openai_rubric_model,
    )


def resolve_provider_for_user(db: Session, user: User | None):
    """
    The provider that should grade for this professor.

    Falls back to the administrator's provider whenever the professor has
    not chosen their own - including when their chosen credential has gone
    missing, so a deleted key degrades to "the shared account" rather than
    failing a whole batch.
    """
    from backend.ai.providers import get_provider

    if user is None or not user.preferred_provider:
        return get_provider()

    credential = get_credential(db, user, user.preferred_provider)
    if credential is None:
        log_event("provider_credential.missing_fallback", level="warning",
                  user_id=user.id, provider=user.preferred_provider)
        return get_provider()

    api_key = _decrypt(credential.encrypted_key) if credential.encrypted_key else ""
    return _provider_from(credential.provider, api_key,
                          credential.base_url, credential.model)


# ---------------------------------------------------------------------
# Testing a credential
# ---------------------------------------------------------------------
def test_credential(db: Session, user: User, provider: str) -> ProviderCredential:
    """
    Make one tiny real call so a professor learns their key works here,
    rather than when a batch of 200 fails.

    The outcome is recorded on the row; the key itself never leaves this
    function.
    """
    credential = get_credential(db, user, provider)
    if credential is None:
        raise CredentialError(f"No saved credentials for '{provider}'.")

    api_key = _decrypt(credential.encrypted_key) if credential.encrypted_key else ""
    built = _provider_from(credential.provider, api_key,
                           credential.base_url, credential.model)

    ok, detail = True, "Connected."
    try:
        # The smallest possible round-trip that proves credentials, network
        # and model name are all right.
        result, _usage = built.complete_json(
            system="Reply with JSON only.",
            user_prompt='Return exactly {"ok": true}',
            schema={"type": "object",
                    "properties": {"ok": {"type": "boolean"}},
                    "required": ["ok"], "additionalProperties": False},
            effort="low", purpose="rubric",
        )
        detail = f"Connected. Model replied: {result}"
    except Exception as exc:  # noqa: BLE001 - the message is the product here
        ok = False
        detail = str(exc)[:400]

    credential.last_tested_at = datetime.utcnow()
    credential.last_test_ok = ok
    credential.last_test_detail = detail
    db.commit()
    db.refresh(credential)
    log_event("provider_credential.tested", user_id=user.id,
              provider=provider, ok=ok, level="info" if ok else "warning")
    return credential


def discover_local_models(base_url: str | None = None) -> dict[str, Any]:
    """
    Ask an Ollama server which models it has pulled.

    Ollama's native listing lives at /api/tags, one level above the
    OpenAI-compatible /v1 path, so the configured base URL is trimmed back
    to the host. Returns a dict rather than raising: "is Ollama reachable?"
    is a question the Settings page asks routinely and a connection refused
    is an ordinary answer, not an error.
    """
    import requests

    url = (base_url or settings.local_base_url or "").strip()
    root = url.rstrip("/")
    for suffix in ("/v1", "/api"):
        if root.endswith(suffix):
            root = root[: -len(suffix)]
    if not root:
        return {"reachable": False, "models": [],
                "detail": "No local base URL configured."}

    try:
        response = requests.get(f"{root}/api/tags", timeout=5)
        response.raise_for_status()
        models = [m.get("name") for m in response.json().get("models", [])]
        return {"reachable": True, "models": [m for m in models if m],
                "detail": f"{len(models)} model(s) available at {root}",
                "base_url": f"{root}/v1"}
    except Exception as exc:  # noqa: BLE001 - unreachable is a normal answer
        return {"reachable": False, "models": [],
                "detail": f"Could not reach an Ollama server at {root}: "
                          f"{type(exc).__name__}",
                "base_url": f"{root}/v1"}


# ---------------------------------------------------------------------
# Canvas credentials (per instructor)
# ---------------------------------------------------------------------
def get_canvas_credential(db: Session, user: User):
    """This instructor's saved Canvas connection, if any."""
    from backend.models.canvas_credential import CanvasCredential

    return (
        db.query(CanvasCredential)
        .filter(CanvasCredential.user_id == user.id)
        .first()
    )


def save_canvas_credential(db: Session, user: User, *, base_url: str,
                           api_token: str | None = None):
    """
    Save or update this instructor's Canvas connection.

    `api_token=None` keeps the stored token, so the URL can be corrected
    without re-pasting it.
    """
    from backend.models.canvas_credential import CanvasCredential

    base_url = (base_url or "").strip().rstrip("/")
    if not base_url:
        raise CredentialError(
            "A Canvas URL is required, for example https://canvas.your-uni.edu"
        )
    if not base_url.startswith(("http://", "https://")):
        raise CredentialError("The Canvas URL must start with https://")

    credential = get_canvas_credential(db, user)
    if credential is None:
        if not (api_token or "").strip():
            raise CredentialError("A Canvas access token is required.")
        credential = CanvasCredential(user_id=user.id, base_url=base_url,
                                      encrypted_token=b"")
        db.add(credential)

    credential.base_url = base_url
    if api_token is not None and api_token.strip():
        token = api_token.strip()
        credential.encrypted_token = _encrypt(token)
        credential.token_hint = token[-4:]
    credential.last_tested_at = None
    credential.last_test_ok = None
    credential.last_test_detail = None
    credential.canvas_user_name = None
    credential.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(credential)
    log_event("canvas_credential.saved", user_id=user.id, base_url=base_url)
    return credential


def delete_canvas_credential(db: Session, user: User) -> bool:
    credential = get_canvas_credential(db, user)
    if credential is None:
        return False
    db.delete(credential)
    db.commit()
    log_event("canvas_credential.deleted", user_id=user.id)
    return True


def canvas_credentials_for(db: Session, user: User | None):
    """
    The (base_url, token) this request should talk to Canvas with.

    Falls back to the server-wide values in .env when the instructor has
    not connected their own - which is what a single-instructor install
    uses, and keeps every existing deployment working unchanged.
    """
    if user is None:
        return None, None
    credential = get_canvas_credential(db, user)
    if credential is None or not credential.encrypted_token:
        return None, None
    return credential.base_url, _decrypt(credential.encrypted_token)


def test_canvas_credential(db: Session, user: User):
    """
    Ask Canvas who this token belongs to.

    `/users/self` is the cheapest call that proves the URL, the token and
    the network path all work, and it returns a name the instructor can
    recognise - so a token pasted from the wrong account is obvious.
    """
    import httpx

    from backend.services import canvas_service

    credential = get_canvas_credential(db, user)
    if credential is None:
        raise CredentialError("No Canvas connection saved yet.")

    base_url, token = canvas_credentials_for(db, user)
    ok, detail, who = True, "Connected.", None
    try:
        response = httpx.get(
            f"{base_url}/api/v1/users/self",
            headers={"Authorization": f"Bearer {token}",
                     "Accept": "application/json"},
            timeout=canvas_service.REQUEST_TIMEOUT, follow_redirects=True,
        )
        if response.status_code == 401:
            ok, detail = False, ("Canvas rejected the token. Generate a new "
                                 "one under Account -> Settings.")
        elif response.status_code >= 400:
            ok, detail = False, f"Canvas returned {response.status_code}."
        else:
            who = response.json().get("name")
            detail = f"Connected to {base_url} as {who}."
    except Exception as exc:  # noqa: BLE001 - the message is the product here
        ok = False
        detail = f"Could not reach {base_url}: {type(exc).__name__}"

    credential.last_tested_at = datetime.utcnow()
    credential.last_test_ok = ok
    credential.last_test_detail = detail[:400]
    credential.canvas_user_name = who
    db.commit()
    db.refresh(credential)
    log_event("canvas_credential.tested", user_id=user.id, ok=ok,
              level="info" if ok else "warning")
    return credential
