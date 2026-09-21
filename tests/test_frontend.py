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

from backend.version import APP_VERSION

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
                 canvas_configured: bool = False, courses=UNSET,
                 signup_open: bool = True, needs_first_account: bool = False,
                 provider_credentials=None, preferred_provider=None):
        self.anthropic_configured = anthropic_configured
        self.canvas_configured = canvas_configured
        self.courses = COURSE if courses is FakeBackend.UNSET else courses
        self.signup_open = signup_open
        self.needs_first_account = needs_first_account
        self.provider_credentials = provider_credentials or []
        self.preferred_provider = preferred_provider

    # -- status --
    def health(self):
        return {"status": "ok", "version": APP_VERSION, "environment": "test",
                "anthropic_configured": self.anthropic_configured,
                "canvas_configured": self.canvas_configured}

    def canvas_status(self):
        return {"configured": self.canvas_configured, "base_url": None}

    def registration_status(self):
        # These key names are the contract with GET
        # /api/auth/registration-status. They are pinned by
        # test_registration_status_field_names_are_a_contract.
        return {"open": self.signup_open,
                "needs_first_account": self.needs_first_account}

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
                "credentials": self.provider_credentials,
                "preferred_provider": self.preferred_provider,
                "using_administrator": self.preferred_provider is None,
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



def page_text(app) -> str:
    """
    Everything the page actually renders, as one string.

    `str(app)` prints AppTest's own repr, which omits the markdown - so an
    assertion against it passes or fails for the wrong reason.
    """
    parts: list[str] = []
    for name in ("title", "header", "subheader", "markdown", "caption",
                 "text", "success", "info", "warning", "error"):
        for element in getattr(app, name, []):
            parts.append(str(getattr(element, "value", "")))
    for name in ("button", "text_input", "selectbox", "checkbox", "radio"):
        for widget in getattr(app, name, []):
            parts.append(str(getattr(widget, "label", "")))
    return "\n".join(parts)

def run_page(path: Path, *, signed_in: bool = True, is_admin: bool = False,
             session_state: dict | None = None) -> AppTest:
    app = AppTest.from_file(str(path), default_timeout=30)
    if signed_in:
        app.session_state["token"] = "fake-token"
        app.session_state["user"] = dict(USER, is_admin=is_admin)
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


def test_a_shipped_instance_does_not_offer_account_creation(fake_backend):
    """
    Sign-up is closed on a real installation. Offering a button that can
    only answer 403 sends a colleague looking for a bug that is not there.
    """
    fake_backend(signup_open=False, needs_first_account=False)
    app = run_page(PAGES["app"], signed_in=False)
    assert not app.exception
    assert "Create account" not in {b.label for b in app.button}
    assert "Sign in to start" in {b.label for b in app.button}


def test_a_fresh_install_does_offer_account_creation(fake_backend):
    """Otherwise nobody could ever set one up."""
    fake_backend(signup_open=False, needs_first_account=True)
    app = run_page(PAGES["app"], signed_in=False)
    assert "Create account" in {b.label for b in app.button}


def test_the_sign_in_view_says_where_accounts_come_from(fake_backend):
    fake_backend(signup_open=False, needs_first_account=False)
    app = run_page(PAGES["app"], signed_in=False,
                   session_state={"ag_view": "signin"})
    assert not app.exception
    captions = " ".join(c.value for c in app.caption)
    assert "administrator" in captions
    assert "Create an account" not in {b.label for b in app.button}


def test_the_sign_up_view_is_refused_when_signup_is_closed(fake_backend):
    """Reaching it by a stale link must not present an unusable form."""
    fake_backend(signup_open=False, needs_first_account=False)
    app = run_page(PAGES["app"], signed_in=False,
                   session_state={"ag_view": "signup"})
    assert not app.exception
    labels = {w.label for w in app.text_input}
    assert "Full name" not in labels
    assert "Email" in labels and "Password" in labels


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


def test_home_sends_you_to_settings_when_no_provider_is_set_up(fake_backend):
    """
    This used to name an environment variable. A professor who installed
    the package has no .env open and no reason to know what one is; the
    only useful thing to say is where to click.
    """
    fake_backend(anthropic_configured=False)
    app = run_page(PAGES["app"])
    warnings = " ".join(w.value for w in app.warning)
    assert "not set up" in warnings
    assert ".env" not in warnings
    assert "API_KEY" not in warnings


def test_home_says_nothing_when_the_user_has_their_own_key(fake_backend):
    """The server having no key is irrelevant to someone who brought one."""
    fake_backend(anthropic_configured=False,
                 provider_credentials=[SAVED_KEY],
                 preferred_provider="openai")
    app = run_page(PAGES["app"])
    warnings = " ".join(w.value for w in app.warning)
    assert "not set up" not in warnings


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
    assert "No AI provider is set up" in errors
    assert ".env" not in errors


def test_upload_page_offers_grading_when_configured(fake_backend):
    fake_backend(anthropic_configured=True)
    app = run_page(PAGES["upload_grade"])
    assert not app.exception
    labels = [b.label for b in app.button]
    assert any("Grade" in label for label in labels)


# ---------------------------------------------------------------------
# Review results
# ---------------------------------------------------------------------
def _set_radio(app, key, value):
    for widget in app.radio:
        if widget.key == key:
            return widget.set_value(value).run()
    raise AssertionError(f"no radio with key {key}")


def test_review_page_shows_one_submission_and_filters_by_status(fake_backend):
    """
    The queue shows one submission at a time (that is what keeps a big class
    fast), and the status filter chooses which submissions are in the queue.
    """
    fake_backend()
    app = run_page(PAGES["review_results"])
    assert not app.exception
    # Default "Needs approval" -> the open submission (Bob) is shown.
    assert "Bob Smith" in page_text(app)
    # Switching to "Approved" brings up the finalized one (Alice).
    app = _set_radio(app, "rr_filter_a1", "Approved")
    assert not app.exception
    assert "Alice Chen" in page_text(app)


def test_review_page_locks_scores_on_an_approved_grade(fake_backend):
    """A finalized grade shows its scores but never lets you edit them."""
    fake_backend()
    app = run_page(PAGES["review_results"])
    assert not app.exception

    # Default filter shows the open submission (g2) - it is editable.
    open_inputs = [
        n for n in app.number_input if n.key and n.key.startswith("score_g2_")
    ]
    assert open_inputs, "an open result should show editable scores"
    assert all(not n.disabled for n in open_inputs)

    # The approved submission (g1) shows its scores, disabled.
    app = _set_radio(app, "rr_filter_a1", "Approved")
    finalized_inputs = [
        n for n in app.number_input if n.key and n.key.startswith("score_g1_")
    ]
    assert finalized_inputs, "the approved result should still show its scores"
    assert all(n.disabled for n in finalized_inputs)


def test_review_page_can_bulk_approve_unflagged(fake_backend, monkeypatch):
    """
    'Approve all' clears the graded, unflagged, not-yet-approved backlog in
    one confirmed click, and never touches flagged ones.
    """
    fake_backend()
    from frontend_streamlit.components import api_client

    clean = {**RESULTS[1], "id": "g3", "flags": [], "finalized": False,
             "student_name": "Carol Ng"}
    monkeypatch.setattr(api_client, "list_results", lambda *a, **k: [clean])
    seen: dict = {}
    monkeypatch.setattr(
        api_client, "finalize_all",
        lambda aid, skip_flagged=True: (seen.update(aid=aid, skip=skip_flagged)
                                        or {"finalized": 1}),
    )

    app = run_page(PAGES["review_results"])
    approve = [b for b in app.button if b.label and "Approve all" in b.label]
    assert approve, "a graded, unflagged, unapproved result should offer bulk approve"

    app = approve[0].click().run()
    yes = [b for b in app.button if b.label and "Yes, approve" in b.label]
    assert yes, "bulk approve must confirm before acting"
    yes[0].click().run()
    assert seen == {"aid": "a1", "skip": True}


def test_review_page_offers_a_direct_final_score(fake_backend):
    """
    An editable result must let the professor enter a final score in one
    field, without touching every section - the fast path for a submission
    graded by hand.
    """
    fake_backend()
    app = run_page(PAGES["review_results"])
    assert not app.exception

    # g2 is not finalized - it offers the direct final-score input.
    total_inputs = [
        n for n in app.number_input if n.key and n.key.startswith("total_g2")
    ]
    assert total_inputs, "an editable result should offer a final-score field"
    labels = " ".join(str(m.value) for m in app.markdown)
    assert "Final score" in labels


def test_review_page_locks_sections_under_a_manual_total(fake_backend, monkeypatch):
    """
    Once a manual final score is set, the section scores are shown but
    disabled (they no longer drive the total), and the page says so.
    """
    fake_backend()
    from frontend_streamlit.components import api_client

    manual = {**RESULTS[1], "id": "g2", "total_override": 42.0,
              "effective_score": 42.0, "finalized": False}
    monkeypatch.setattr(api_client, "list_results", lambda *a, **k: [manual])

    app = run_page(PAGES["review_results"])
    assert not app.exception

    section_inputs = [
        n for n in app.number_input if n.key and n.key.startswith("score_g2_")
    ]
    assert section_inputs, "sections should still be visible under a manual total"
    assert all(n.disabled for n in section_inputs)
    infos = " ".join(str(i.value) for i in app.info)
    assert "manual final score" in infos.lower()


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
    """
    It has to send them where the fix is. That used to be `.env`; now
    each instructor connects their own Canvas in the interface, and a
    message still naming an environment variable would strand them.
    """
    fake_backend(canvas_configured=False)
    app = run_page(PAGES["export"])
    assert not app.exception
    infos = " ".join(i.value for i in app.info)
    assert "Settings" in infos and "Canvas" in infos
    assert "CANVAS_BASE_URL" not in infos
    assert ".env" not in infos


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


# ---------------------------------------------------------------------
# Settings - the two pages a professor has to get right before grading
# ---------------------------------------------------------------------
SAVED_KEY = {
    "provider": "openai", "masked_key": "****ab12", "has_key": True,
    "base_url": None, "model": "gpt-4o", "last_tested_at": None,
    "last_test_ok": True, "last_test_detail": "Reached OpenAI.",
}


def test_a_fresh_install_says_grading_is_not_set_up_yet(fake_backend):
    """
    The first thing a professor sees on this page decides whether they
    know what to do next. With no key anywhere, it has to say so.
    """
    fake_backend(anthropic_configured=False)
    app = run_page(PAGES["settings_providers"])
    assert not app.exception
    warnings = " ".join(w.value for w in app.warning)
    assert "not set up" in warnings.lower()


def test_a_saved_key_is_reported_as_working(fake_backend):
    fake_backend(anthropic_configured=False,
                 provider_credentials=[SAVED_KEY],
                 preferred_provider="openai")
    app = run_page(PAGES["settings_providers"])
    assert not app.exception
    successes = " ".join(s.value for s in app.success)
    assert "Grading is set up" in successes
    assert "gpt-4o" in successes


def test_the_providers_page_never_shows_a_whole_key(fake_backend):
    fake_backend(provider_credentials=[SAVED_KEY], preferred_provider="openai")
    app = run_page(PAGES["settings_providers"])
    rendered = page_text(app)
    assert "ab12" in rendered          # the masked tail is fine
    assert "sk-a" not in rendered      # a real key never is


def test_the_providers_page_offers_all_three_providers(fake_backend):
    fake_backend()
    app = run_page(PAGES["settings_providers"])
    assert not app.exception
    rendered = page_text(app)
    for expected in ("OpenAI", "Claude", "Ollama"):
        assert expected in rendered


def test_the_canvas_page_explains_where_the_token_comes_from(fake_backend):
    """A professor who cannot find the token cannot use Canvas at all."""
    fake_backend()
    app = run_page(PAGES["settings_canvas"])
    assert not app.exception
    rendered = page_text(app)
    assert "Approved Integrations" in rendered
    assert "New Access Token" in rendered


def test_the_export_page_lets_you_set_the_canvas_ids(fake_backend):
    """
    These used to be dead-end warnings, one of which told a professor to
    "edit it via the API" - for a value the interface could only set while
    the course was being created. Connect Canvas after making your course
    and there was no way forward but to delete and recreate it.
    """
    fake_backend(canvas_configured=True)
    app = run_page(PAGES["export"])
    assert not app.exception
    labels = {w.label for w in app.text_input}
    assert "Canvas course ID" in labels
    assert "Canvas assignment ID" in labels
    assert "Save Canvas IDs" in {b.label for b in app.button}
    assert "via the API" not in page_text(app)


def test_the_shared_key_is_described_differently_to_its_owner(fake_backend):
    """
    "The cost goes to them, not to you" is true for a colleague on a shared
    server and nonsense for the administrator reading it on their own
    machine - they are them.
    """
    fake_backend(anthropic_configured=True)

    colleague = page_text(run_page(PAGES["settings_providers"], is_admin=False))
    assert "goes to them, not to you" in colleague
    assert "shared account on this server" in colleague

    owner = page_text(run_page(PAGES["settings_providers"], is_admin=True))
    assert "goes to them, not to you" not in owner
    assert "settings file" in owner


def test_the_sidebar_names_the_key_correctly_for_each_reader(fake_backend):
    """The status line had the same "shared account" problem as the page."""
    fake_backend(anthropic_configured=True)

    colleague = page_text(run_page(PAGES["dashboard"], is_admin=False))
    assert "the shared OpenAI account" in colleague

    owner = page_text(run_page(PAGES["dashboard"], is_admin=True))
    assert "the OpenAI key on this computer" in owner
    assert "shared" not in owner.split("Ready to grade")[1][:80]
