"""
Canvas LMS integration.

Three jobs:
  * pull the roster, so submissions get real names and Canvas user ids
  * pull assignment metadata, so points possible line up
  * push grades and feedback back into the Canvas gradebook

Canvas' API is paginated with RFC 5988 `Link` headers and rate-limited
with a leaky-bucket "X-Rate-Limit-Remaining" header. Both are handled
here so callers just get lists back.

Configuration lives in .env (CANVAS_BASE_URL, CANVAS_API_TOKEN). When it
is absent every function raises CanvasNotConfigured rather than failing
obscurely mid-request - Canvas is optional and the app works without it.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any, Iterator

import httpx

from backend.config import settings

logger = logging.getLogger(__name__)

# Canvas caps page size at 100 for most endpoints.
PAGE_SIZE = 100
REQUEST_TIMEOUT = 30.0
MAX_RETRIES = 3

# Canvas throttles by cost, not request count. Below this we back off.
LOW_RATE_LIMIT = 50.0

_NEXT_LINK = re.compile(r'<([^>]+)>;\s*rel="next"')


class CanvasError(RuntimeError):
    """Any failure talking to Canvas."""


class CanvasNotConfigured(CanvasError):
    """Raised when Canvas credentials are missing from .env."""


def is_configured() -> bool:
    """True when both CANVAS_BASE_URL and CANVAS_API_TOKEN are set."""
    return bool(settings.canvas_base_url and settings.canvas_api_token)


def _require_config() -> tuple[str, str]:
    if not is_configured():
        raise CanvasNotConfigured(
            "Canvas is not configured. Set CANVAS_BASE_URL and "
            "CANVAS_API_TOKEN in your .env file - see docs/canvas_setup.md."
        )
    return settings.canvas_base_url.rstrip("/"), settings.canvas_api_token


def _client() -> httpx.Client:
    base_url, token = _require_config()
    return httpx.Client(
        base_url=f"{base_url}/api/v1",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        timeout=REQUEST_TIMEOUT,
        follow_redirects=True,
    )


def _check_response(response: httpx.Response) -> None:
    """Turn Canvas' error responses into messages a professor can act on."""
    if response.is_success:
        return

    if response.status_code == 401:
        raise CanvasError(
            "Canvas rejected the API token. Generate a new one under "
            "Account -> Settings -> Approved Integrations."
        )
    if response.status_code == 403:
        raise CanvasError(
            "Canvas returned 403. The token is valid but lacks permission "
            "for this course, or the rate limit was exceeded."
        )
    if response.status_code == 404:
        raise CanvasError(
            f"Canvas returned 404 for {response.request.url.path}. "
            f"Check the course/assignment id."
        )

    try:
        detail = response.json()
    except Exception:  # noqa: BLE001 - Canvas sometimes returns HTML
        detail = response.text[:300]
    raise CanvasError(f"Canvas API error {response.status_code}: {detail}")


def _throttle(response: httpx.Response) -> None:
    """Pause when Canvas says the leaky bucket is nearly empty."""
    remaining = response.headers.get("X-Rate-Limit-Remaining")
    if remaining is None:
        return
    try:
        if float(remaining) < LOW_RATE_LIMIT:
            logger.info("Canvas rate limit low (%s); backing off 2s", remaining)
            time.sleep(2.0)
    except ValueError:
        pass


def _paginate(path: str, params: dict[str, Any] | None = None) -> Iterator[dict]:
    """
    Yield every item across all pages of a Canvas list endpoint.

    Follows the `Link: rel="next"` header rather than incrementing a page
    counter, which is what Canvas' docs require.
    """
    params = {**(params or {}), "per_page": PAGE_SIZE}

    with _client() as client:
        url: str | None = path
        first = True
        while url:
            for attempt in range(MAX_RETRIES):
                try:
                    response = client.get(url, params=params if first else None)
                    break
                except httpx.RequestError as exc:
                    if attempt == MAX_RETRIES - 1:
                        raise CanvasError(f"Could not reach Canvas: {exc}") from exc
                    time.sleep(2 ** attempt)

            _check_response(response)
            _throttle(response)

            payload = response.json()
            if isinstance(payload, list):
                yield from payload
            else:
                yield payload

            match = _NEXT_LINK.search(response.headers.get("Link", ""))
            url = match.group(1) if match else None
            first = False


# ---------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------
def list_courses() -> list[dict[str, Any]]:
    """Courses the token's owner teaches."""
    return [
        {
            "canvas_course_id": str(c["id"]),
            "name": c.get("name") or "(unnamed course)",
            "course_code": c.get("course_code"),
            "term": (c.get("term") or {}).get("name"),
        }
        for c in _paginate("/courses", {"enrollment_type": "teacher",
                                        "state[]": "available"})
        if "id" in c
    ]


def list_assignments(canvas_course_id: str) -> list[dict[str, Any]]:
    """Assignments in one Canvas course."""
    return [
        {
            "canvas_assignment_id": str(a["id"]),
            "name": a.get("name") or "(unnamed assignment)",
            "points_possible": a.get("points_possible"),
            "due_at": a.get("due_at"),
            "published": a.get("published", False),
        }
        for a in _paginate(f"/courses/{canvas_course_id}/assignments")
        if "id" in a
    ]


def get_roster(canvas_course_id: str) -> list[dict[str, Any]]:
    """
    Active students in a Canvas course.

    Returns the fields we need to match an uploaded file to a student:
    canvas id, name, sortable name, login and SIS ids, and email.
    """
    roster: list[dict[str, Any]] = []
    for user in _paginate(
        f"/courses/{canvas_course_id}/users",
        {"enrollment_type[]": "student", "enrollment_state[]": "active",
         "include[]": "email"},
    ):
        if "id" not in user:
            continue
        roster.append({
            "canvas_user_id": str(user["id"]),
            "name": user.get("name") or "",
            "sortable_name": user.get("sortable_name") or "",
            "login_id": user.get("login_id") or "",
            "sis_user_id": user.get("sis_user_id") or "",
            "email": user.get("email") or "",
        })
    return roster


# ---------------------------------------------------------------------
# Roster matching
# ---------------------------------------------------------------------
def _normalize(name: str) -> str:
    return re.sub(r"[^a-z]", "", (name or "").lower())


def match_student(
    roster: list[dict[str, Any]],
    *,
    name: str | None = None,
    email: str | None = None,
) -> dict[str, Any] | None:
    """
    Find a roster entry for an uploaded submission.

    Email is authoritative when present. Otherwise we compare
    letters-only forms of the name, trying "First Last", the Canvas
    "Last, First" sortable form, and finally a surname-only match - which
    is what a filename like `chenalice_12345_hw3.ipynb` gives us.

    Returns None when nothing matches confidently; the professor then
    fixes it by hand rather than the system guessing wrong.
    """
    if email:
        target = email.strip().lower()
        for entry in roster:
            if entry["email"].lower() == target or entry["login_id"].lower() == target:
                return entry

    if not name:
        return None

    target = _normalize(name)
    if not target:
        return None

    for entry in roster:
        if _normalize(entry["name"]) == target:
            return entry
        # Canvas sortable_name is "Chen, Alice" -> "chenalice"
        if _normalize(entry["sortable_name"]) == target:
            return entry

    # Reversed word order: "Alice Chen" vs "Chen Alice"
    reversed_target = _normalize(" ".join(reversed(name.split())))
    for entry in roster:
        if _normalize(entry["name"]) == reversed_target:
            return entry

    return None


# ---------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------
def push_grade(
    canvas_course_id: str,
    canvas_assignment_id: str,
    canvas_user_id: str,
    score: float,
    comment: str | None = None,
) -> dict[str, Any]:
    """
    Push one grade (and optionally a comment) into the Canvas gradebook.

    Canvas overwrites whatever grade was there, so callers should only
    push finalized grades.
    """
    _require_config()
    payload: dict[str, Any] = {"submission[posted_grade]": score}
    if comment:
        # Canvas truncates very long comments; keep it to a readable size.
        payload["comment[text_comment]"] = comment[:4000]

    with _client() as client:
        try:
            response = client.put(
                f"/courses/{canvas_course_id}/assignments/"
                f"{canvas_assignment_id}/submissions/{canvas_user_id}",
                data=payload,
            )
        except httpx.RequestError as exc:
            raise CanvasError(f"Could not reach Canvas: {exc}") from exc

    _check_response(response)
    return response.json()


def push_grades_bulk(
    canvas_course_id: str,
    canvas_assignment_id: str,
    grades: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Push many grades in one Canvas request.

    `grades` entries are {"canvas_user_id", "score", "comment"}.

    Canvas processes this asynchronously and returns a progress object;
    the returned dict includes its `progress_url` so a caller can poll.
    One failing student does not roll back the others.
    """
    _require_config()
    if not grades:
        return {"submitted": 0, "progress_url": None}

    payload: dict[str, Any] = {}
    for entry in grades:
        uid = entry["canvas_user_id"]
        payload[f"grade_data[{uid}][posted_grade]"] = entry["score"]
        if entry.get("comment"):
            payload[f"grade_data[{uid}][text_comment]"] = entry["comment"][:4000]

    with _client() as client:
        try:
            response = client.post(
                f"/courses/{canvas_course_id}/assignments/"
                f"{canvas_assignment_id}/submissions/update_grades",
                data=payload,
            )
        except httpx.RequestError as exc:
            raise CanvasError(f"Could not reach Canvas: {exc}") from exc

    _check_response(response)
    body = response.json()
    return {
        "submitted": len(grades),
        "progress_url": body.get("url"),
        "progress_id": body.get("id"),
        "workflow_state": body.get("workflow_state"),
    }


def check_progress(progress_url: str) -> dict[str, Any]:
    """Poll a Canvas Progress object returned by a bulk update."""
    _require_config()
    with _client() as client:
        try:
            response = client.get(progress_url)
        except httpx.RequestError as exc:
            raise CanvasError(f"Could not reach Canvas: {exc}") from exc
    _check_response(response)
    body = response.json()
    return {
        "workflow_state": body.get("workflow_state"),
        "completion": body.get("completion"),
        "message": body.get("message"),
    }
