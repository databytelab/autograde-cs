"""
Centralized API client for Streamlit - all requests go through here.
Automatically attaches the JWT token from session state.

Every function returns either the decoded body or None. On failure the
error is rendered into the page with `st.error`, so pages can write

    courses = list_courses()
    if courses is None:
        st.stop()

and never have to build their own error handling.
"""
from __future__ import annotations

import os
from typing import Any

import requests
import streamlit as st

API_BASE = os.environ.get("AUTOGRADE_API_BASE", "http://localhost:8000")

# Grading a full class is slow by design - one Claude call per submission.
GRADING_TIMEOUT = 1800  # 30 minutes
DEFAULT_TIMEOUT = 60


def api_call(
    method: str,
    endpoint: str,
    *,
    quiet: bool = False,
    raw: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    **kwargs: Any,
):
    """
    Make an authenticated API call.

    `quiet=True` suppresses the on-page error (useful when a 404 is an
    expected outcome). `raw=True` returns the Response object instead of
    parsed JSON, for file downloads.
    """
    headers = kwargs.pop("headers", {})
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{API_BASE}{endpoint}"
    try:
        response = requests.request(
            method, url, headers=headers, timeout=timeout, **kwargs
        )
        response.raise_for_status()
        if raw:
            return response
        return response.json() if response.content else {}

    except requests.exceptions.ConnectionError:
        if not quiet:
            st.error(
                f"Cannot reach the backend at {API_BASE}. "
                f"Start it with:  uvicorn backend.main:app --reload"
            )
        return None

    except requests.exceptions.Timeout:
        if not quiet:
            st.error("The request timed out. The backend may still be working.")
        return None

    except requests.exceptions.HTTPError as exc:
        response = exc.response
        # An expired or invalid token: send the user back to the login page.
        if response.status_code == 401 and st.session_state.get("token"):
            st.session_state.pop("token", None)
            st.session_state.pop("user", None)
            st.warning("Your session expired. Please sign in again.")
            st.rerun()

        if not quiet:
            st.error(f"{response.status_code} - {_error_detail(response)}")
        return None


def _error_detail(response: requests.Response) -> str:
    """Pull a readable message out of the API's error body."""
    try:
        body = response.json()
    except ValueError:
        return response.text[:300] or response.reason

    detail = body.get("detail", "")
    problems = body.get("problems")
    if problems:
        listed = "; ".join(f"{p['field']}: {p['message']}" for p in problems)
        return f"{detail} ({listed})"
    return str(detail) or response.reason


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------
def login(email: str, password: str) -> bool:
    body = api_call("POST", "/api/auth/login-json",
                    json={"email": email, "password": password})
    if not body:
        return False
    st.session_state["token"] = body["access_token"]
    st.session_state["user"] = body["user"]
    return True


def register(email: str, name: str, password: str, role: str = "professor") -> bool:
    body = api_call("POST", "/api/auth/register", json={
        "email": email, "name": name, "password": password, "role": role,
    })
    if not body:
        return False
    st.session_state["token"] = body["access_token"]
    st.session_state["user"] = body["user"]
    return True


def logout() -> None:
    for key in ("token", "user", "active_course", "active_assignment"):
        st.session_state.pop(key, None)


def health() -> dict | None:
    return api_call("GET", "/api/health", quiet=True)


# ---------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------
def list_courses():
    return api_call("GET", "/api/courses")


def create_course(name: str, term: str | None, canvas_course_id: str | None = None):
    return api_call("POST", "/api/courses", json={
        "name": name, "term": term or None,
        "canvas_course_id": canvas_course_id or None,
    })


def delete_course(course_id: str):
    return api_call("DELETE", f"/api/courses/{course_id}")


# ---------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------
def list_assignments(course_id: str | None = None):
    endpoint = "/api/assignments"
    if course_id:
        endpoint += f"?course_id={course_id}"
    return api_call("GET", endpoint)


def get_assignment(assignment_id: str):
    return api_call("GET", f"/api/assignments/{assignment_id}")


def create_assignment(payload: dict):
    return api_call("POST", "/api/assignments", json=payload, timeout=300)


def update_assignment(assignment_id: str, payload: dict):
    return api_call("PATCH", f"/api/assignments/{assignment_id}", json=payload)


def delete_assignment(assignment_id: str):
    return api_call("DELETE", f"/api/assignments/{assignment_id}")


def get_rubric(assignment_id: str):
    return api_call("GET", f"/api/assignments/{assignment_id}/rubric")


def preview_rubric(text: str, total_points: float | None = None):
    return api_call("POST", "/api/assignments/rubric/preview", timeout=300,
                    json={"text": text, "total_points": total_points})


def upload_solution(assignment_id: str, file) -> dict | None:
    return api_call(
        "POST", f"/api/assignments/{assignment_id}/solution",
        files={"file": (file.name, file.getvalue())},
    )


# ---------------------------------------------------------------------
# Submissions and grading
# ---------------------------------------------------------------------
def upload_submissions(assignment_id: str, files: list) -> dict | None:
    payload = [("files", (f.name, f.getvalue())) for f in files]
    return api_call(
        "POST", f"/api/assignments/{assignment_id}/submissions",
        files=payload, timeout=600,
    )


def list_submissions(assignment_id: str):
    return api_call("GET", f"/api/assignments/{assignment_id}/submissions")


def update_submission(submission_id: str, payload: dict):
    return api_call("PATCH", f"/api/submissions/{submission_id}", json=payload)


def delete_submission(submission_id: str):
    return api_call("DELETE", f"/api/submissions/{submission_id}")


def grade(assignment_id: str, *, submission_ids: list[str] | None = None,
          regrade: bool = False, include_images: bool = True):
    return api_call(
        "POST", f"/api/assignments/{assignment_id}/grade",
        timeout=GRADING_TIMEOUT,
        json={"submission_ids": submission_ids, "regrade": regrade,
              "include_images": include_images},
    )


# ---------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------
def list_results(assignment_id: str, *, flagged_only: bool = False):
    return api_call(
        "GET",
        f"/api/assignments/{assignment_id}/results?flagged_only={str(flagged_only).lower()}",
    )


def get_stats(assignment_id: str):
    return api_call("GET", f"/api/assignments/{assignment_id}/stats")


def override(grade_id: str, overrides: dict, summary_feedback: str | None = None):
    payload: dict[str, Any] = {"overrides": overrides}
    if summary_feedback is not None:
        payload["summary_feedback"] = summary_feedback
    return api_call("PATCH", f"/api/results/{grade_id}/override", json=payload)


def finalize(grade_id: str, finalized: bool = True):
    return api_call("POST", f"/api/results/{grade_id}/finalize",
                    json={"finalized": finalized})


# ---------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------
def scan_similarity(assignment_id: str, threshold: float = 0.5):
    return api_call(
        "POST", f"/api/assignments/{assignment_id}/similarity", timeout=600,
        json={"threshold": threshold, "clear_existing": True},
    )


def list_similarity(assignment_id: str):
    return api_call("GET", f"/api/assignments/{assignment_id}/similarity")


def review_similarity(flag_id: str, reviewed: bool, note: str | None = None):
    return api_call("PATCH", f"/api/similarity/{flag_id}",
                    json={"reviewed": reviewed, "professor_note": note})


# ---------------------------------------------------------------------
# Export and Canvas
# ---------------------------------------------------------------------
def export_bytes(assignment_id: str, fmt: str, only_finalized: bool = False):
    """Returns (content, filename) or None."""
    response = api_call(
        "GET",
        f"/api/assignments/{assignment_id}/export"
        f"?format={fmt}&only_finalized={str(only_finalized).lower()}",
        raw=True, timeout=300,
    )
    if response is None:
        return None

    disposition = response.headers.get("content-disposition", "")
    filename = "grades"
    if "filename=" in disposition:
        filename = disposition.split("filename=")[-1].strip('"; ')
    return response.content, filename


def canvas_status():
    return api_call("GET", "/api/canvas/status", quiet=True)


def canvas_sync_roster(assignment_id: str):
    return api_call("POST",
                    f"/api/assignments/{assignment_id}/canvas/sync-roster",
                    timeout=300)


def canvas_push_grades(assignment_id: str, only_finalized: bool = True):
    return api_call(
        "POST",
        f"/api/assignments/{assignment_id}/canvas/push-grades"
        f"?only_finalized={str(only_finalized).lower()}",
        timeout=300,
    )
