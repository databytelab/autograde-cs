"""Streamlit frontend tests - Stage 9.

Uses Streamlit's own `AppTest` harness, which executes a page script the
way the server would and reports any exception it raised. Every API call
is stubbed, so these tests prove the pages *render* - the import path, the
auth guard, the widget wiring, and the response-shape assumptions - without
a backend or a browser.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

FRONTEND = Path(__file__).resolve().parents[1] / "frontend_streamlit"

PAGES = {
    "app": FRONTEND / "app.py",
    "dashboard": FRONTEND / "pages" / "dashboard.py",
    "new_assignment": FRONTEND / "pages" / "new_assignment.py",
    "upload_grade": FRONTEND / "pages" / "upload_grade.py",
    "review_results": FRONTEND / "pages" / "review_results.py",
    "export": FRONTEND / "pages" / "export.py",
    "settings_providers": FRONTEND / "pages" / "settings_providers.py",
    "settings_canvas": FRONTEND / "pages" / "settings_canvas.py",
    "settings_account": FRONTEND / "pages" / "settings_account.py",
}


# ---------------------------------------------------------------------
# Fake backend
# ---------------------------------------------------------------------
USER = {"id": "u1", "email": "prof@university.edu", "name": "Dr. Ada Lovelace",
        "role": "professor", "is_active": True, "created_at": "2026-01-01T00:00:00"}

COURSE = {"id": "c1", "user_id": "u1", "name": "CS 231N", "term": "Fall 2025",
          "canvas_course_id": None, "assignment_count": 1,
          "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00"}

ASSIGNMENT = {
    "id": "a1", "course_id": "c1", "name": "HW3", "description": "Fit a model.",
    "status": "complete", "total_possible_points": 100.0,
    "submission_count": 2, "graded_count": 2, "due_date": None,
    "canvas_assignment_id": None, "expected_submission_path": None,
    "rubric_json": None, "rubric_raw_text": None,
    "created_at": "2026-01-01T00:00:00", "updated_at": "2026-01-01T00:00:00",
}

STATS = {
    "assignment_id": "a1", "assignment_name": "HW3", "total_submissions": 2,
    "graded": 2, "pending": 0, "errored": 0, "finalized": 1, "flagged": 1,
    "mean_percentage": 84.5, "median_percentage": 84.5,
    "min_percentage": 80.0, "max_percentage": 89.0,
    "grade_distribution": {"B+": 1, "B-": 1},
}

SUBMISSIONS = [
    {"id": "s1", "assignment_id": "a1", "student_name": "Alice Chen",
     "student_email": "alice@university.edu", "student_id_external": None,
     "original_filename": "alice_hw3.ipynb", "file_type": "ipynb",
     "file_size_bytes": 4096, "status": "graded", "error_message": None,
     "submitted_at": "2026-01-01T00:00:00", "graded_at": "2026-01-02T00:00:00"},
    {"id": "s2", "assignment_id": "a1", "student_name": "Bob Smith",
     "student_email": None, "student_id_external": None,
     "original_filename": "bob_hw3.py", "file_type": "py",
     "file_size_bytes": 2048, "status": "flagged", "error_message": None,
     "submitted_at": "2026-01-01T00:00:00", "graded_at": "2026-01-02T00:00:00"},
]

RESULTS = [
    {"id": "g1", "submission_id": "s1", "student_name": "Alice Chen",
     "original_filename": "alice_hw3.ipynb",
     "total_score": 89.0, "total_possible": 100.0, "percentage": 89.0,
     "letter_grade": "B+", "effective_score": 89.0, "flags": [],
     "professor_overrides": None, "finalized": True,
     "finalized_at": "2026-01-03T00:00:00",
     "summary_feedback": "Solid work overall.",
     "criteria_results": [
         {"criterion_id": "loading", "name": "Data loading", "score": 27.0,
          "max_score": 30.0, "reasoning": "CSV read correctly.",
          "feedback": "Good.", "flags": []},
         {"criterion_id": "model", "name": "Model fitting", "score": 40.0,
          "max_score": 45.0, "reasoning": "pinv used.", "feedback": "Nice.",
          "flags": []},
     ],
     "ai_raw_output": {"summary_feedback": "Solid work overall."},
     "created_at": "2026-01-02T00:00:00", "updated_at": "2026-01-02T00:00:00"},
    {"id": "g2", "submission_id": "s2", "student_name": "Bob Smith",
     "original_filename": "bob_hw3.py",
     "total_score": 80.0, "total_possible": 100.0, "percentage": 80.0,
     "letter_grade": "B-", "effective_score": 80.0,
     "flags": ["no_outputs"], "professor_overrides": None,
     "finalized": False, "finalized_at": None,
     "summary_feedback": "Run your notebook before submitting.",
     "criteria_results": [
         {"criterion_id": "loading", "name": "Data loading", "score": 20.0,
          "max_score": 30.0, "reasoning": "No output recorded.",
          "feedback": "Run the cell.", "flags": ["no_outputs"]},
         {"criterion_id": "model", "name": "Model fitting", "score": 60.0,
          "max_score": 45.0, "reasoning": "", "feedback": "", "flags": []},
     ],
     "ai_raw_output": {}, "created_at": "2026-01-02T00:00:00",
     "updated_at": "2026-01-02T00:00:00"},
]

FLAGS = [{
    "id": "f1", "assignment_id": "a1", "submission_a_id": "s1",
    "submission_b_id": "s2", "similarity_score": 0.93, "severity": "high",
    "method": "combined", "reviewed": False, "professor_note": None,
    "student_a_name": "Alice Chen", "student_b_name": "Bob Smith",
    "created_at": "2026-01-02T00:00:00",
}]


class FakeBackend:
    """Stand-in for every api_client function a page might call."""

    # Distinguishes "caller said nothing" from "caller said: no courses".
    UNSET = object()

    def __init__(self, *, anthropic_configured: bool = True,
                 canvas_configured: bool = False, courses=UNSET):
        self.anthropic_configured = anthropic_configured
        self.canvas_configured = canvas_configured
        self.courses = COURSE if courses is FakeBackend.UNSET else courses

    # -- status --
    def health(self):
        return {"status": "ok", "version": "1.0.0", "environment": "test",
                "anthropic_configured": self.anthropic_configured,
                "canvas_configured": self.canvas_configured}

    def canvas_status(self):
        return {"configured": self.canvas_configured, "base_url": None}

    # -- reads --
    def list_courses(self):
        return [self.courses] if self.courses else []

    def list_assignments(self, course_id=None):
        return [ASSIGNMENT] if self.courses else []

    def get_assignment(self, assignment_id):
        return ASSIGNMENT

    def get_stats(self, assignment_id):
        return STATS

    def list_submissions(self, assignment_id):
        return SUBMISSIONS

    def list_results(self, assignment_id, flagged_only=False):
        return [r for r in RESULTS if r["flags"]] if flagged_only else RESULTS

    def list_similarity(self, assignment_id):
        return FLAGS

    def get_rubric(self, assignment_id):
        return {"title": "R", "total_points": 100.0, "criteria": [], "warnings": []}

    # -- writes (never exercised unless a test clicks) --
    def create_course(self, *a, **k):
        return COURSE

    def create_assignment(self, payload):
        return ASSIGNMENT

    def preview_rubric(self, text, total_points=None):
        return {"title": "Preview", "total_points": 100.0, "warnings": [],
                "criteria": [{"id": "x", "name": "X", "description": "d",
                              "max_points": 100.0, "keywords": [],
                              "requires_output": False}]}

    def export_bytes(self, assignment_id, fmt, only_finalized=False):
        return b"col\n1\n", f"grades.{fmt}"

    # -- settings pages --
    def provider_settings(self):
        return {"supported": ["openai", "anthropic", "local"],
                "credentials": [], "preferred_provider": None,
                "using_administrator": True,
                "administrator_provider": "openai",
                "administrator_available": self.anthropic_configured}

    def canvas_settings(self):
        return {"connected": False, "base_url": None, "masked_token": "",
                "canvas_user_name": None, "last_tested_at": None,
                "last_test_ok": None, "last_test_detail": None,
                "server_fallback_available": self.canvas_configured}

    def list_users(self):
        return [dict(USER, is_admin=True)]

    def __getattr__(self, name):
        """Any other call returns a benign truthy dict."""
        return lambda *a, **k: {}


@pytest.fixture
def fake_backend(monkeypatch):
    """Install a FakeBackend over the api_client module."""
    from frontend_streamlit.components import api_client

    def install(**kwargs) -> FakeBackend:
        backend = FakeBackend(**kwargs)
        for attribute in dir(api_client):
            if attribute.startswith("_"):
                continue
            if callable(getattr(api_client, attribute, None)):
                replacement = getattr(backend, attribute, None)
                if replacement is not None and callable(replacement):
                    monkeypatch.setattr(api_client, attribute, replacement)
        return backend

    return install


def run_page(path: Path, *, signed_in: bool = True,
             session_state: dict | None = None) -> AppTest:
    app = AppTest.from_file(str(path), default_timeout=30)
    if signed_in:
        app.session_state["token"] = "fake-token"
        app.session_state["user"] = USER
    for key, value in (session_state or {}).items():
        app.session_state[key] = value
    return app.run()


# ---------------------------------------------------------------------
# Every page renders
# ---------------------------------------------------------------------
@pytest.mark.parametrize("name", list(PAGES))
def test_page_renders_without_error(name, fake_backend):
    """The single most valuable frontend test: does the script run at all."""
    fake_backend()
    app = run_page(PAGES[name])
    assert not app.exception, (
        f"{name} raised: "
        f"{[e.value for e in app.exception]}"
    )


@pytest.mark.parametrize("name", [n for n in PAGES if n != "app"])
def test_pages_require_sign_in(name, fake_backend):
    """A signed-out visitor must be stopped, not shown someone's grades."""
    fake_backend()
    app = run_page(PAGES[name], signed_in=False)
    assert not app.exception
    assert any("sign in" in w.value.lower() for w in app.warning), \
        f"{name} did not ask the visitor to sign in"


# ---------------------------------------------------------------------
# Home
# ---------------------------------------------------------------------
def test_home_shows_the_landing_page_when_signed_out(fake_backend):
    """
    The signed-out home is the marketing surface: the pitch, the workflow
    and the two calls to action. The credential fields live in the auth
    view that those buttons open (see the test below), not in the hero.
    """
    fake_backend()
    app = run_page(PAGES["app"], signed_in=False)
    assert not app.exception
    button_labels = {b.label for b in app.button}
    assert "Sign in to start" in button_labels
    assert "Create account" in button_labels


def test_home_shows_the_credential_fields_in_the_auth_view(fake_backend):
    """Choosing "Sign in to start" must lead to a real, usable form."""
    import streamlit as st

    fake_backend()
    app = run_page(PAGES["app"], signed_in=False,
                   session_state={"ag_view": "signin"})
    assert not app.exception
    labels = {w.label for w in app.text_input}
    assert "Email" in labels
    assert "Password" in labels


def test_home_warns_when_no_api_key(fake_backend):
    fake_backend(anthropic_configured=False)
    app = run_page(PAGES["app"])
    warnings = " ".join(w.value for w in app.warning)
    assert "ANTHROPIC_API_KEY" in warnings


def test_home_does_not_warn_when_the_key_is_present(fake_backend):
    fake_backend(anthropic_configured=True)
    app = run_page(PAGES["app"])
    warnings = " ".join(w.value for w in app.warning)
    assert "ANTHROPIC_API_KEY" not in warnings


# ---------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------
def test_dashboard_shows_the_headline_metrics(fake_backend):
    fake_backend()
    app = run_page(PAGES["dashboard"])
    assert not app.exception
    values = [m.value for m in app.metric]
    assert "1" in values          # one course
    assert any("/" in str(v) for v in values)   # the graded ratio


def test_dashboard_prompts_when_there_are_no_courses(fake_backend):
    fake_backend(courses=None)
    app = run_page(PAGES["dashboard"])
    assert not app.exception
    assert any("no courses" in i.value.lower() for i in app.info)


# ---------------------------------------------------------------------
# Upload & grade
# ---------------------------------------------------------------------
def test_upload_page_disables_grading_without_a_key(fake_backend):
    fake_backend(anthropic_configured=False)
    app = run_page(PAGES["upload_grade"])
    assert not app.exception
    errors = " ".join(e.value for e in app.error)
    assert "Grading is unavailable" in errors


def test_upload_page_offers_grading_when_configured(fake_backend):
    fake_backend(anthropic_configured=True)
    app = run_page(PAGES["upload_grade"])
    assert not app.exception
    labels = [b.label for b in app.button]
    assert any("Grade" in label for label in labels)


# ---------------------------------------------------------------------
# Review results
# ---------------------------------------------------------------------
def test_review_page_lists_every_result(fake_backend):
    fake_backend()
    app = run_page(PAGES["review_results"])
    assert not app.exception
    rendered = " ".join(str(m.value) for m in app.markdown)
    assert "Alice Chen" in rendered or any(
        "Alice Chen" in str(e) for e in app.get("expander")
    )


def test_review_page_locks_scores_on_an_approved_grade(fake_backend):
    """A finalized grade must not present editable score inputs."""
    fake_backend()
    app = run_page(PAGES["review_results"])
    assert not app.exception

    # g1 is finalized, g2 is not - the finalized one's inputs are disabled.
    finalized_inputs = [
        n for n in app.number_input if n.key and n.key.startswith("score_g1_")
    ]
    open_inputs = [
        n for n in app.number_input if n.key and n.key.startswith("score_g2_")
    ]
    assert finalized_inputs, "the approved result should still show its scores"
    assert all(n.disabled for n in finalized_inputs)
    assert all(not n.disabled for n in open_inputs)


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------
def test_export_page_offers_all_four_formats(fake_backend):
    fake_backend()
    app = run_page(PAGES["export"])
    assert not app.exception
    labels = " ".join(b.label for b in app.button)
    for expected in ("CSV", "Excel", "PDF feedback", "Canvas CSV"):
        assert expected in labels


def test_export_page_explains_a_missing_canvas_config(fake_backend):
    fake_backend(canvas_configured=False)
    app = run_page(PAGES["export"])
    assert not app.exception
    infos = " ".join(i.value for i in app.info)
    assert "CANVAS_BASE_URL" in infos


def test_export_page_flags_unapproved_grades(fake_backend):
    fake_backend()
    app = run_page(PAGES["export"])
    infos = " ".join(i.value for i in app.info)
    assert "not approved yet" in infos


# ---------------------------------------------------------------------
# New assignment
# ---------------------------------------------------------------------
def test_new_assignment_offers_all_rubric_routes(fake_backend):
    fake_backend()
    app = run_page(PAGES["new_assignment"])
    assert not app.exception
    options = app.radio[0].options
    assert len(options) == 4
    assert any("Describe" in o for o in options)
    assert any("solution file" in o for o in options)
    assert any("JSON" in o for o in options)
    assert any("default" in o for o in options)
