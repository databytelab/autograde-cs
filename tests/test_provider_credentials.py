"""
Bring-your-own-key: encryption, isolation, masking, and never leaking.

The security properties here are the whole point of the feature, so they
are tested as properties rather than as happy paths: a key must not be
readable from the database, must not come back from any endpoint, must not
be reachable by another professor, and must not appear in a log line.
"""
from __future__ import annotations

import json

import pytest

from backend.models.provider_credential import ProviderCredential
from backend.models.user import User


def _register(client, email: str, name: str = "Prof"):
    response = client.post("/api/auth/register", json={
        "email": email, "name": name, "password": "a-good-password-here",
        "role": "professor"})
    assert response.status_code == 201, response.text
    body = response.json()
    return {"user": body["user"],
            "headers": {"Authorization": f"Bearer {body['access_token']}"}}


SECRET = "sk-test-abcdefghijklmnop-SECRET-1234"


# ---------------------------------------------------------------------
# Storage and masking
# ---------------------------------------------------------------------
def test_a_saved_key_is_encrypted_at_rest(client, db_session, professor):
    """The plaintext must not be findable anywhere in the row."""
    saved = client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    assert saved.status_code == 200, saved.text

    row = db_session.query(ProviderCredential).filter(
        ProviderCredential.provider == "openai").one()
    assert row.encrypted_key is not None
    assert SECRET.encode() not in row.encrypted_key
    assert SECRET not in str(row.__dict__)


def test_the_api_never_returns_the_key(client, professor):
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])

    body = client.get("/api/settings/providers",
                      headers=professor["headers"]).text
    assert SECRET not in body
    assert "1234" in body, "the last four should be shown so it is recognisable"

    parsed = json.loads(body)
    entry = next(c for c in parsed["credentials"] if c["provider"] == "openai")
    assert entry["masked_key"] == "****1234"
    assert entry["has_key"] is True
    assert "api_key" not in entry and "encrypted_key" not in entry


def test_a_saved_key_round_trips_for_grading(client, db_session, professor):
    """Encrypted at rest, but still usable - otherwise it is just a shredder."""
    from backend.services.credential_service import get_credential, _decrypt

    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    user = db_session.get(User, professor["user"]["id"])
    credential = get_credential(db_session, user, "openai")
    assert _decrypt(credential.encrypted_key) == SECRET


def test_replacing_a_key_overwrites_the_old_one(client, db_session, professor):
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": "sk-replacement-key-9999"},
        headers=professor["headers"])

    rows = db_session.query(ProviderCredential).filter(
        ProviderCredential.provider == "openai").all()
    assert len(rows) == 1, "replacing must not leave the previous key behind"
    body = client.get("/api/settings/providers",
                      headers=professor["headers"]).json()
    entry = next(c for c in body["credentials"] if c["provider"] == "openai")
    assert entry["masked_key"] == "****9999"


def test_saving_without_a_key_keeps_the_existing_one(client, professor):
    """Changing the model must not force a professor to re-type their key."""
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    client.put("/api/settings/providers", json={
        "provider": "openai", "model": "gpt-4o-mini"},
        headers=professor["headers"])

    body = client.get("/api/settings/providers",
                      headers=professor["headers"]).json()
    entry = next(c for c in body["credentials"] if c["provider"] == "openai")
    assert entry["has_key"] is True
    assert entry["masked_key"] == "****1234"
    assert entry["model"] == "gpt-4o-mini"


def test_removing_a_key_deletes_it(client, db_session, professor):
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    assert client.delete("/api/settings/providers/openai",
                         headers=professor["headers"]).status_code == 200
    assert db_session.query(ProviderCredential).count() == 0


# ---------------------------------------------------------------------
# Isolation
# ---------------------------------------------------------------------
def test_credentials_are_isolated_between_professors(client, professor):
    """The core promise: my key is mine."""
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])

    other = _register(client, "other@university.edu", "Other Prof")
    body = client.get("/api/settings/providers", headers=other["headers"]).json()
    assert body["credentials"] == []
    assert body["using_administrator"] is True

    # There is no endpoint that takes a user id, so the only thing to try is
    # deleting/testing by provider name - which must act on their own row.
    assert client.delete("/api/settings/providers/openai",
                         headers=other["headers"]).status_code == 404
    assert client.post("/api/settings/providers/openai/test",
                       headers=other["headers"]).status_code == 404

    # ...and the owner's key is untouched.
    mine = client.get("/api/settings/providers",
                      headers=professor["headers"]).json()
    assert mine["credentials"][0]["masked_key"] == "****1234"


def test_provider_settings_require_authentication(client):
    assert client.get("/api/settings/providers").status_code == 401
    assert client.put("/api/settings/providers",
                      json={"provider": "openai", "api_key": "x"}).status_code == 401


# ---------------------------------------------------------------------
# Choosing whose key grades
# ---------------------------------------------------------------------
def test_saving_a_key_does_not_switch_grading_to_it(client, professor):
    """Pasting a key must not silently redirect a course's spend."""
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    body = client.get("/api/settings/providers",
                      headers=professor["headers"]).json()
    assert body["using_administrator"] is True
    assert body["preferred_provider"] is None


def test_switching_to_a_personal_key_and_back(client, professor):
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])

    switched = client.put("/api/settings/providers/preference",
                          json={"provider": "openai"},
                          headers=professor["headers"])
    assert switched.status_code == 200
    assert switched.json()["preferred_provider"] == "openai"
    assert switched.json()["using_administrator"] is False

    back = client.put("/api/settings/providers/preference",
                      json={"provider": None}, headers=professor["headers"])
    assert back.json()["using_administrator"] is True


def test_cannot_select_a_provider_with_no_saved_key(client, professor):
    response = client.put("/api/settings/providers/preference",
                          json={"provider": "anthropic"},
                          headers=professor["headers"])
    assert response.status_code == 422
    assert "not saved" in response.json()["detail"].lower()


def test_removing_the_selected_key_reverts_to_the_administrator(client, professor):
    """A deleted key must not leave grading pointing at nothing."""
    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    client.put("/api/settings/providers/preference", json={"provider": "openai"},
               headers=professor["headers"])

    after = client.delete("/api/settings/providers/openai",
                          headers=professor["headers"]).json()
    assert after["using_administrator"] is True
    assert after["preferred_provider"] is None


def test_an_unsupported_provider_is_rejected(client, professor):
    response = client.put("/api/settings/providers", json={
        "provider": "definitely-not-a-provider", "api_key": "x"},
        headers=professor["headers"])
    assert response.status_code == 422


def test_a_local_provider_requires_a_base_url(client, professor):
    response = client.put("/api/settings/providers", json={
        "provider": "local", "api_key": ""}, headers=professor["headers"])
    assert response.status_code == 422
    assert "base url" in response.json()["detail"].lower()


def test_a_local_provider_needs_no_api_key(client, professor):
    response = client.put("/api/settings/providers", json={
        "provider": "local", "base_url": "http://ollama:11434/v1",
        "model": "qwen2.5-coder:7b"}, headers=professor["headers"])
    assert response.status_code == 200
    entry = next(c for c in response.json()["credentials"]
                 if c["provider"] == "local")
    assert entry["has_key"] is False
    assert entry["base_url"] == "http://ollama:11434/v1"


# ---------------------------------------------------------------------
# Which provider actually grades
# ---------------------------------------------------------------------
def test_resolution_uses_the_administrator_by_default(db_session, professor):
    from backend.services.credential_service import resolve_provider_for_user

    user = db_session.get(User, professor["user"]["id"])
    from backend.ai.providers import get_provider
    assert resolve_provider_for_user(db_session, user) is get_provider()


def test_resolution_uses_the_professors_own_key_when_selected(
        client, db_session, professor):
    from backend.services.credential_service import resolve_provider_for_user

    client.put("/api/settings/providers", json={
        "provider": "local", "base_url": "http://my-ollama:11434/v1",
        "model": "qwen2.5-coder:7b"}, headers=professor["headers"])
    client.put("/api/settings/providers/preference", json={"provider": "local"},
               headers=professor["headers"])

    user = db_session.get(User, professor["user"]["id"])
    resolved = resolve_provider_for_user(db_session, user)
    assert resolved.name == "local"
    assert resolved._base_url == "http://my-ollama:11434/v1"
    assert resolved._grading_model == "qwen2.5-coder:7b"


def test_a_missing_credential_falls_back_instead_of_failing(
        client, db_session, professor):
    """
    A deleted row behind a stale preference must degrade to the shared
    account, not fail a whole batch.
    """
    from backend.ai.providers import get_provider
    from backend.services.credential_service import resolve_provider_for_user

    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": SECRET}, headers=professor["headers"])
    client.put("/api/settings/providers/preference", json={"provider": "openai"},
               headers=professor["headers"])

    db_session.query(ProviderCredential).delete()
    db_session.commit()

    user = db_session.get(User, professor["user"]["id"])
    user.preferred_provider = "openai"          # stale preference
    assert resolve_provider_for_user(db_session, user) is get_provider()


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
def test_saving_a_key_does_not_log_it(client, professor, caplog):
    with caplog.at_level("INFO"):
        client.put("/api/settings/providers", json={
            "provider": "openai", "api_key": SECRET},
            headers=professor["headers"])
    assert SECRET not in caplog.text
    assert "provider_credential.saved" in caplog.text


def test_log_redaction_covers_credential_field_names():
    """Even a future caller that passes a key by name must not leak it."""
    from backend.utils.logging_utils import _clean

    for field in ("api_key", "apiKey", "password", "secret_key", "authorization"):
        assert _clean(field, SECRET) == "[redacted]"


# ---------------------------------------------------------------------
# Ollama discovery
# ---------------------------------------------------------------------
def test_local_discovery_reports_unreachable_without_raising(client, professor):
    """'Is Ollama reachable?' has a normal negative answer, not an exception."""
    response = client.get(
        "/api/settings/providers/local/discover?base_url=http://127.0.0.1:9/v1",
        headers=professor["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["reachable"] is False
    assert body["models"] == []


def test_local_discovery_lists_models(client, professor, monkeypatch):
    from backend.services import credential_service

    class _Response:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"models": [{"name": "qwen2.5-coder:7b"},
                               {"name": "llama3.1:8b"}]}

    # discover_local_models imports requests inside the function, so
    # patching the module attribute is what it will actually see.
    import requests as _requests
    monkeypatch.setattr(_requests, "get", lambda *a, **k: _Response())
    assert credential_service.discover_local_models is not None

    body = client.get(
        "/api/settings/providers/local/discover?base_url=http://ollama:11434/v1",
        headers=professor["headers"]).json()
    assert body["reachable"] is True
    assert "qwen2.5-coder:7b" in body["models"]
    # The /v1 suffix is trimmed before asking Ollama's native endpoint.
    assert body["base_url"] == "http://ollama:11434/v1"


# ---------------------------------------------------------------------
# Bringing your own Claude key
# ---------------------------------------------------------------------
def test_a_personal_claude_key_builds_a_provider():
    """
    AnthropicProvider took no arguments, so every path that passed a
    professor's own key - Test connection, and grading itself - died with
    `TypeError: AnthropicProvider() takes no arguments`. OpenAI and local
    already accepted credentials, so only Claude was broken, and only for
    users who brought their own key.
    """
    from backend.services.credential_service import _provider_from

    built = _provider_from("anthropic", "sk-ant-a-professors-own-key",
                           None, "claude-sonnet-5")
    assert built.name == "anthropic"
    assert built._model_for("grading") == "claude-sonnet-5"


def test_claude_without_a_personal_key_still_uses_the_shared_client():
    """The server-wide account must keep working exactly as before."""
    from backend.ai.providers.anthropic_provider import AnthropicProvider
    from backend.config import settings

    shared = AnthropicProvider()
    assert shared._model_for("grading") == settings.anthropic_grading_model
    assert shared._api_key is None


def test_testing_an_unbuildable_credential_reports_instead_of_exploding(
        client, db_session, professor, monkeypatch):
    """
    Test connection exists to explain what is wrong. A provider that
    cannot even be constructed used to escape as an HTTP 500 from that
    very button - the professor got "Internal Server Error" and no clue.
    """
    from backend.services import credential_service

    client.put("/api/settings/providers", json={
        "provider": "openai", "api_key": "sk-whatever"},
        headers=professor["headers"])

    def explode(*_args, **_kwargs):
        raise TypeError("provider cannot be built")

    monkeypatch.setattr(credential_service, "_provider_from", explode)
    response = client.post("/api/settings/providers/openai/test",
                           headers=professor["headers"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["last_test_ok"] is False
    assert "cannot be built" in body["last_test_detail"]


# ---------------------------------------------------------------------
# The rubric calls have to use the same credentials as grading
# ---------------------------------------------------------------------
def test_building_a_rubric_uses_the_professors_own_provider(
        client, db_session, professor, monkeypatch):
    """
    Rubric generation used the server-wide provider. On a single-professor
    installation there is no server-wide provider, so the very first thing
    they do - turn a marking scheme into a rubric - failed with a message
    telling them to edit .env.
    """
    from backend.ai import grader

    client.put("/api/settings/providers", json={
        "provider": "local", "base_url": "http://my-ollama:11434/v1",
        "model": "qwen2.5-coder:7b"}, headers=professor["headers"])
    client.put("/api/settings/providers/preference", json={"provider": "local"},
               headers=professor["headers"])

    used = {}

    def fake_extract(text, total_points=None, provider=None):
        used["provider"] = provider
        return {"title": "R", "total_points": 100,
                "criteria": [{"id": "c1", "name": "Correctness",
                              "description": "It works.", "max_points": 100}]}

    monkeypatch.setattr(grader, "extract_rubric_from_text", fake_extract)
    response = client.post("/api/assignments/rubric/preview", json={
        "text": "Write a function (100 points).", "total_points": 100},
        headers=professor["headers"])

    assert response.status_code == 200, response.text
    assert used["provider"] is not None, "fell back to the server-wide provider"
    assert used["provider"].name == "local"
