"""
Shared UI pieces used by every page.

`require_auth()` is the guard each page calls first - Streamlit runs page
scripts top to bottom on every interaction, so the check has to be a
plain function call at the top of the file rather than a decorator.
"""
from __future__ import annotations

from html import escape
from typing import Any

import streamlit as st

from frontend_streamlit.components import api_client

# The .env variable a professor must set for each provider, shown in the
# "grading disabled" message so the fix is obvious.
_KEY_HINT = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "local": "a running local model server (see LOCAL_BASE_URL)",
}


def grading_ready(status: dict[str, Any] | None) -> bool:
    """
    Whether the backend can actually grade right now.

    Prefers the provider-agnostic `llm_configured`, falling back to the older
    `anthropic_configured` so a backend that predates the provider switch
    still reports correctly.
    """
    if not status:
        return False
    return bool(status.get("llm_configured", status.get("anthropic_configured", False)))


def grading_key_hint(status: dict[str, Any] | None) -> str:
    """The provider name and the env var to set, e.g. 'OPENAI_API_KEY'."""
    provider = (status or {}).get("llm_provider", "anthropic")
    return _KEY_HINT.get(provider, "ANTHROPIC_API_KEY")


# Matches the letter grades from backend/services/rubric_service.py
GRADE_COLORS = {
    "A+": "#1B7F3B", "A": "#1B7F3B", "A-": "#2E9E52",
    "B+": "#5A8F2E", "B": "#5A8F2E", "B-": "#7FA33A",
    "C+": "#B58A1B", "C": "#B58A1B", "C-": "#C79A2E",
    "D+": "#C4611F", "D": "#C4611F", "D-": "#C4611F",
    "F":  "#B02020",
}

FLAG_LABELS = {
    "no_outputs": "Never executed",
    "runtime_error": "Runtime error",
    "incomplete": "Incomplete",
    "possible_ai_generated": "Possibly AI-generated",
    "output_mismatch": "Output mismatch",
    "grader_error": "Grader error - review manually",
    "score_clamped": "Score clamped to the maximum",
    "prompt_injection": "Tried to instruct the grader - review manually",
}


# A small, font-size-only bump: Streamlit's default body text reads a touch
# small. Nothing else here - no colours, layout, or navigation.
_TEXT_CSS = """
<style>
.stApp p, .stApp li, .stApp label,
[data-testid="stMarkdownContainer"] p { font-size: 16.5px; line-height: 1.55; }
[data-testid="stCaptionContainer"] p, [data-testid="stCaptionContainer"] {
  font-size: 0.95rem !important;
}
</style>
"""


def page_setup(title: str, icon: str | None = None) -> None:
    """Standard page config. Call once, first, on every page."""
    st.set_page_config(page_title=f"{title} - AutoGrade CS", layout="wide")
    st.markdown(_TEXT_CSS, unsafe_allow_html=True)


def require_auth() -> dict[str, Any]:
    """
    Stop the page unless the user is signed in.

    Returns the current user dict. Renders the sidebar as a side effect,
    so pages get consistent navigation for free.
    """
    if not st.session_state.get("token"):
        st.warning("Please sign in on the **Home** page first.")
        try:
            st.page_link("app.py", label="Go to sign in", icon=":material/login:")
        except Exception:  # noqa: BLE001 - see _workflow_links
            pass
        st.stop()

    user = st.session_state["user"]
    render_sidebar(user)
    return user


WORKFLOW = [
    ("app.py", "Home", ":material/home:"),
    ("pages/dashboard.py", "1 · Dashboard", ":material/space_dashboard:"),
    ("pages/new_assignment.py", "2 · New assignment", ":material/note_add:"),
    ("pages/upload_grade.py", "3 · Upload & grade", ":material/upload_file:"),
    ("pages/review_results.py", "4 · Review results", ":material/fact_check:"),
    ("pages/export.py", "5 · Export", ":material/download:"),
]

# Kept apart from the numbered steps: these are configured once and then
# forgotten, not part of grading a batch.
SETTINGS = [
    ("pages/settings_providers.py", "AI providers", ":material/key:"),
    ("pages/settings_canvas.py", "Canvas", ":material/school:"),
    ("pages/settings_account.py", "Account", ":material/person:"),
]


def page_link(target: str, label: str, icon: str | None = None) -> None:
    """
    A `st.page_link` that cannot crash the page.

    Streamlit resolves a page_link target relative to the *main* script,
    so these paths only exist when the app was launched from `app.py` as
    intended. Running a page file directly - or rendering it in a test
    harness - makes every link unresolvable, which would otherwise raise
    and take the whole page down. Degrade to a caption instead.
    """
    try:
        st.page_link(target, label=label, icon=icon)
    except Exception:  # noqa: BLE001 - StreamlitAPIException and friends
        st.caption(f"{icon or ''} {label}".strip())


def _workflow_links() -> None:
    """The five workflow steps, in the order a professor performs them."""
    for target, label, icon in WORKFLOW:
        page_link(target, label, icon)


def _settings_links() -> None:
    for target, label, icon in SETTINGS:
        page_link(target, label, icon)


# How each provider is named to a professor, who cares which service their
# students' work is sent to - not which key happens to be set.
_PROVIDER_LABEL = {
    "openai": "the OpenAI API",
    "anthropic": "the Claude API",
    "local": "a local model",
}


def _backend_status_line() -> None:
    """Shared sidebar footer: is the API reachable, is grading configured?"""
    status = api_client.health()
    if status is None:
        st.error("Backend offline - start the API server")
    elif not grading_ready(status):
        st.warning(f"Grading unavailable - set {grading_key_hint(status)}")
    else:
        provider = status.get("llm_provider", "")
        st.success(f"Ready to grade - using {_PROVIDER_LABEL.get(provider, provider)}")


def render_sidebar(user: dict[str, Any]) -> None:
    """Identity, workflow links, and backend status."""
    with st.sidebar:
        st.markdown(f"**{user['name']}**")
        st.caption(f"{user['email']} · {user['role']}")

        st.divider()
        st.markdown("**Workflow**")
        _workflow_links()

        st.markdown("**Settings**")
        _settings_links()

        st.divider()
        _backend_status_line()

        if st.button("Sign out", use_container_width=True):
            api_client.logout()
            st.rerun()


# ---------------------------------------------------------------------
# Selectors
# ---------------------------------------------------------------------
def course_selector(label: str = "Course", key: str = "course_select"):
    """
    Course dropdown that remembers the choice across pages.

    Returns the selected course dict, or None if the user has no courses.
    """
    courses = api_client.list_courses()
    if courses is None:
        st.stop()
    if not courses:
        st.info("You have no courses yet. Create one on the "
                "**New assignment** page.")
        return None

    labels = {
        f"{c['name']}" + (f" · {c['term']}" if c.get("term") else ""): c
        for c in courses
    }
    remembered = st.session_state.get("active_course")
    options = list(labels)
    index = 0
    if remembered:
        for i, (_, course) in enumerate(labels.items()):
            if course["id"] == remembered:
                index = i
                break

    choice = st.selectbox(label, options, index=index, key=key)
    selected = labels[choice]
    st.session_state["active_course"] = selected["id"]
    return selected


def assignment_selector(course_id: str, label: str = "Assignment",
                        key: str = "assignment_select"):
    """Assignment dropdown scoped to one course."""
    assignments = api_client.list_assignments(course_id)
    if assignments is None:
        st.stop()
    if not assignments:
        st.info("This course has no assignments yet.")
        return None

    labels = {
        f"{a['name']}  ({a['graded_count']}/{a['submission_count']} graded)": a
        for a in assignments
    }
    remembered = st.session_state.get("active_assignment")
    options = list(labels)
    index = 0
    if remembered:
        for i, (_, assignment) in enumerate(labels.items()):
            if assignment["id"] == remembered:
                index = i
                break

    choice = st.selectbox(label, options, index=index, key=key)
    selected = labels[choice]
    st.session_state["active_assignment"] = selected["id"]
    return selected


# ---------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------
def grade_badge(letter: str | None, percentage: float | None) -> str:
    """Coloured HTML badge for a letter grade."""
    if not letter:
        return "<span style='color:#888'>ungraded</span>"
    color = GRADE_COLORS.get(letter, "#555")
    pct = f" · {percentage:g}%" if percentage is not None else ""
    return (
        f"<span style='background:{color};color:white;padding:2px 10px;"
        f"border-radius:10px;font-weight:600;font-size:0.85em'>"
        f"{escape(str(letter))}{pct}</span>"
    )


def flag_chips(flags: list[str]) -> str:
    """
    Human-readable chips for grader flags.

    Escaped, because this is rendered with `unsafe_allow_html=True` and an
    unrecognised flag falls through to the model's own string. Model output
    is shaped by the student's submission, so it is untrusted text and must
    not be able to inject markup into the professor's browser.
    """
    if not flags:
        return ""
    chips = [
        f"<span style='background:#FDEBEB;color:#B02020;padding:2px 8px;"
        f"border-radius:8px;font-size:0.78em;margin-right:5px'>"
        f"{escape(FLAG_LABELS.get(f, str(f)))}</span>"
        for f in flags
    ]
    return "".join(chips)


def stats_row(stats: dict[str, Any]) -> None:
    """The five headline numbers for an assignment."""
    columns = st.columns(5)
    columns[0].metric("Submissions", stats["total_submissions"])
    columns[1].metric("Graded", stats["graded"])
    columns[2].metric("Finalized", stats["finalized"])
    columns[3].metric(
        "Mean",
        f"{stats['mean_percentage']:g}%" if stats["mean_percentage"] is not None
        else "-",
    )
    columns[4].metric("Similarity flags", stats["flagged"],
                      delta=None if not stats["flagged"] else "review")
