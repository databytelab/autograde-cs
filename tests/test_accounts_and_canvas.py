"""
Shipping a package other people install: account management and
per-instructor Canvas credentials.

These cover the two things that had to change for AutoGrade to be handed
to someone else to run: a fresh install must be set up by whoever gets
there first and then close its doors, and Canvas has to belong to the
instructor rather than to the server.
"""
from __future__ import annotations

import pytest

from backend.models.user import User


def _register(client, email, password="a-good-password-here", role="professor"):
    return client.post("/api/auth/register", json={
        "email": email, "name": "Someone", "password": password, "role": role})


def _headers(response):
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


# ---------------------------------------------------------------------
# First-run bootstrap
# ---------------------------------------------------------------------
def test_the_first_account_becomes_the_administrator(client):
    """A fresh install has to be set up by somebody."""
    first = _register(client, "first@uni.edu")
    assert first.status_code == 201
    assert first.json()["user"]["is_admin"] is True


def test_later_accounts_are_not_administrators(client):
    _register(client, "first@uni.edu")
    second = _register(client, "second@uni.edu")
    assert second.json()["user"]["is_admin"] is False


def test_registration_status_field_names_are_a_contract(client):
    """
    The sign-in page decides whether to offer "Create account" from these
    two field names. Renaming one here hides the button on every install
    while every other test still passes, so pin them.
    """
    body = client.get("/api/auth/registration-status").json()
    assert set(body) == {"open", "needs_first_account"}


def test_registration_status_reports_a_fresh_install(client):
    body = client.get("/api/auth/registration-status").json()
    assert body["needs_first_account"] is True

    _register(client, "first@uni.edu")
    body = client.get("/api/auth/registration-status").json()
    assert body["needs_first_account"] is False


# ---------------------------------------------------------------------
# Closing self sign-up
# ---------------------------------------------------------------------
def test_self_signup_can_be_closed(client, monkeypatch):
    """
    A shipped instance must not let anyone who reaches the page create an
    account for themselves.
    """
    from backend.config import settings

    _register(client, "first@uni.edu")          # the administrator
    # A shipped instance is production, where sign-up is closed unless it
    # was deliberately opened. Development stays open so a local install
    # and this suite can create accounts freely.
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "allow_open_registration", False)

    refused = _register(client, "stranger@uni.edu")
    assert refused.status_code == 403
    assert "administrator" in refused.json()["detail"]


def test_the_very_first_account_is_allowed_even_when_signup_is_closed(
        client, monkeypatch):
    """Otherwise a freshly installed instance could never be set up."""
    from backend.config import settings

    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "allow_open_registration", False)
    first = _register(client, "first@uni.edu")
    assert first.status_code == 201
    assert first.json()["user"]["is_admin"] is True


# ---------------------------------------------------------------------
# Administrator account management
# ---------------------------------------------------------------------
def test_an_administrator_can_create_and_list_accounts(client, monkeypatch):
    from backend.config import settings

    admin = _register(client, "admin@uni.edu")
    admin_headers = _headers(admin)
    monkeypatch.setattr(settings, "environment", "production")
    monkeypatch.setattr(settings, "allow_open_registration", False)

    created = client.post("/api/auth/users", json={
        "email": "colleague@uni.edu", "name": "Dr Colleague",
        "password": "their-initial-password", "role": "professor"},
        headers=admin_headers)
    assert created.status_code == 201
    assert created.json()["is_admin"] is False

    # ...and the colleague can sign in with it.
    signed_in = client.post("/api/auth/login-json", json={
        "email": "colleague@uni.edu", "password": "their-initial-password"})
    assert signed_in.status_code == 200

    listed = client.get("/api/auth/users", headers=admin_headers).json()
    assert {u["email"] for u in listed} == {"admin@uni.edu", "colleague@uni.edu"}


def test_a_non_administrator_cannot_manage_accounts(client):
    _register(client, "admin@uni.edu")
    other = _headers(_register(client, "other@uni.edu"))

    assert client.get("/api/auth/users", headers=other).status_code == 403
    assert client.post("/api/auth/users", json={
        "email": "x@uni.edu", "name": "X", "password": "password-here",
        "role": "professor"}, headers=other).status_code == 403


def test_an_administrator_can_reset_a_forgotten_password(client):
    """There is no email reset on a self-hosted box; this is the answer."""
    admin_headers = _headers(_register(client, "admin@uni.edu"))
    victim = _register(client, "forgetful@uni.edu")
    victim_id = victim.json()["user"]["id"]

    reset = client.post(f"/api/auth/users/{victim_id}/reset-password",
                        json={"new_password": "a-brand-new-password"},
                        headers=admin_headers)
    assert reset.status_code == 200
    assert client.post("/api/auth/login-json", json={
        "email": "forgetful@uni.edu",
        "password": "a-brand-new-password"}).status_code == 200


def test_deactivating_an_account_blocks_sign_in(client):
    admin_headers = _headers(_register(client, "admin@uni.edu"))
    leaver = _register(client, "leaver@uni.edu")
    leaver_id = leaver.json()["user"]["id"]

    client.post(f"/api/auth/users/{leaver_id}/deactivate", headers=admin_headers)
    blocked = client.post("/api/auth/login-json", json={
        "email": "leaver@uni.edu", "password": "a-good-password-here"})
    assert blocked.status_code == 403


def test_an_administrator_cannot_lock_themselves_out(client):
    admin = _register(client, "admin@uni.edu")
    admin_id = admin.json()["user"]["id"]
    response = client.post(f"/api/auth/users/{admin_id}/deactivate",
                           headers=_headers(admin))
    assert response.status_code == 400


# ---------------------------------------------------------------------
# Changing your own password
# ---------------------------------------------------------------------
def test_changing_your_own_password(client):
    response = _register(client, "me@uni.edu", password="the-old-password")
    headers = _headers(response)

    changed = client.post("/api/auth/change-password", json={
        "current_password": "the-old-password",
        "new_password": "the-new-password"}, headers=headers)
    assert changed.status_code == 200

    assert client.post("/api/auth/login-json", json={
        "email": "me@uni.edu", "password": "the-new-password"}).status_code == 200
    assert client.post("/api/auth/login-json", json={
        "email": "me@uni.edu", "password": "the-old-password"}).status_code == 401


def test_changing_a_password_requires_the_current_one(client):
    """A borrowed session must not be able to lock the owner out."""
    headers = _headers(_register(client, "me@uni.edu", password="the-old-password"))
    response = client.post("/api/auth/change-password", json={
        "current_password": "not-the-right-one",
        "new_password": "attackers-password"}, headers=headers)
    assert response.status_code == 400


def test_a_short_new_password_is_rejected(client):
    headers = _headers(_register(client, "me@uni.edu", password="the-old-password"))
    response = client.post("/api/auth/change-password", json={
        "current_password": "the-old-password", "new_password": "short"},
        headers=headers)
    assert response.status_code == 422


# ---------------------------------------------------------------------
# Per-instructor Canvas credentials
# ---------------------------------------------------------------------
CANVAS_TOKEN = "canvas-token-abcdefghijklmnop-7788"


def test_canvas_token_is_encrypted_and_masked(client, db_session, professor):
    from backend.models.canvas_credential import CanvasCredential

    saved = client.put("/api/settings/canvas", json={
        "base_url": "https://canvas.uni.edu", "api_token": CANVAS_TOKEN},
        headers=professor["headers"])
    assert saved.status_code == 200, saved.text

    row = db_session.query(CanvasCredential).one()
    assert CANVAS_TOKEN.encode() not in row.encrypted_token

    body = client.get("/api/settings/canvas", headers=professor["headers"]).text
    assert CANVAS_TOKEN not in body
    assert "****7788" in body


def test_canvas_credentials_are_per_instructor(client, professor):
    """
    The reason this exists: one shared token cannot write grades into
    another professor's Canvas course.
    """
    client.put("/api/settings/canvas", json={
        "base_url": "https://canvas.uni.edu", "api_token": CANVAS_TOKEN},
        headers=professor["headers"])

    other = _headers(_register(client, "other@uni.edu"))
    body = client.get("/api/settings/canvas", headers=other).json()
    assert body["connected"] is False
    assert client.delete("/api/settings/canvas", headers=other).status_code == 404


def test_canvas_status_prefers_the_instructors_own_connection(client, professor):
    before = client.get("/api/canvas/status", headers=professor["headers"]).json()
    assert before["configured"] is False

    client.put("/api/settings/canvas", json={
        "base_url": "https://canvas.uni.edu", "api_token": CANVAS_TOKEN},
        headers=professor["headers"])

    after = client.get("/api/canvas/status", headers=professor["headers"]).json()
    assert after["configured"] is True
    assert after["source"] == "personal"
    assert after["base_url"] == "https://canvas.uni.edu"


def test_the_server_wide_canvas_config_still_works(client, professor,
                                                   monkeypatch):
    """A single-instructor install configures Canvas once in .env."""
    from backend.config import settings

    monkeypatch.setattr(settings, "canvas_base_url", "https://canvas.server.edu")
    monkeypatch.setattr(settings, "canvas_api_token", "server-token")

    body = client.get("/api/canvas/status", headers=professor["headers"]).json()
    assert body["configured"] is True
    assert body["source"] == "server"


def test_a_personal_connection_overrides_the_server_one(client, professor,
                                                        monkeypatch):
    from backend.config import settings

    monkeypatch.setattr(settings, "canvas_base_url", "https://canvas.server.edu")
    monkeypatch.setattr(settings, "canvas_api_token", "server-token")
    client.put("/api/settings/canvas", json={
        "base_url": "https://canvas.mine.edu", "api_token": CANVAS_TOKEN},
        headers=professor["headers"])

    body = client.get("/api/canvas/status", headers=professor["headers"]).json()
    assert body["source"] == "personal"
    assert body["base_url"] == "https://canvas.mine.edu"


def test_a_canvas_url_must_be_a_url(client, professor):
    response = client.put("/api/settings/canvas", json={
        "base_url": "canvas.uni.edu", "api_token": CANVAS_TOKEN},
        headers=professor["headers"])
    assert response.status_code == 422
    assert "https" in response.json()["detail"]


def test_the_canvas_url_can_be_corrected_without_retyping_the_token(
        client, professor):
    client.put("/api/settings/canvas", json={
        "base_url": "https://wrong.uni.edu", "api_token": CANVAS_TOKEN},
        headers=professor["headers"])
    client.put("/api/settings/canvas", json={
        "base_url": "https://right.uni.edu"}, headers=professor["headers"])

    body = client.get("/api/settings/canvas", headers=professor["headers"]).json()
    assert body["base_url"] == "https://right.uni.edu"
    assert body["masked_token"] == "****7788"


def test_removing_a_canvas_connection(client, db_session, professor):
    from backend.models.canvas_credential import CanvasCredential

    client.put("/api/settings/canvas", json={
        "base_url": "https://canvas.uni.edu", "api_token": CANVAS_TOKEN},
        headers=professor["headers"])
    assert client.delete("/api/settings/canvas",
                         headers=professor["headers"]).status_code == 200
    assert db_session.query(CanvasCredential).count() == 0


def test_canvas_settings_require_authentication(client):
    assert client.get("/api/settings/canvas").status_code == 401
    assert client.put("/api/settings/canvas", json={
        "base_url": "https://x.edu", "api_token": "t"}).status_code == 401


def test_saving_a_canvas_token_does_not_log_it(client, professor, caplog):
    with caplog.at_level("INFO"):
        client.put("/api/settings/canvas", json={
            "base_url": "https://canvas.uni.edu", "api_token": CANVAS_TOKEN},
            headers=professor["headers"])
    assert CANVAS_TOKEN not in caplog.text
    assert "canvas_credential.saved" in caplog.text


def test_production_closes_signup_by_default():
    """
    An installer who never edits .env must still get a closed instance.
    The default has to be safe, not merely documented.
    """
    from backend.config import Settings

    shipped = Settings(environment="production", _env_file=None)
    assert shipped.allow_open_registration is False
    assert shipped.registration_is_open() is False

    opened = Settings(environment="production", allow_open_registration=True,
                      _env_file=None)
    assert opened.registration_is_open() is True

    # ...but a local install and the test-suite stay frictionless.
    assert Settings(environment="development",
                    _env_file=None).registration_is_open() is True
