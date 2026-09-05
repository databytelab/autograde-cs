"""FastAPI endpoint tests - Stage 7.

Covers the contract of every route: status codes, auth, ownership
isolation, and validation. Grading endpoints run against the mocked
Claude client, so nothing here touches the network.
"""
from __future__ import annotations

import pytest

from tests.conftest import (
    SAMPLES, SIMPLE_RUBRIC, grade_now, grading_payload, upload_sample,
)


# ---------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------
def test_health_is_public(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    # tells an operator whether grading will actually work
    assert body["anthropic_configured"] is False
    assert body["canvas_configured"] is False


def test_openapi_schema_builds(client):
    """A broken response_model shows up here before it shows up in prod."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.json()["info"]["title"] == "AutoGrade CS"


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------
def test_register_returns_a_token(client):
    response = client.post("/api/auth/register", json={
        "email": "New.Prof@University.edu", "name": "New Prof",
        "password": "a-good-password", "role": "professor",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    # email is normalised to lowercase
    assert body["user"]["email"] == "new.prof@university.edu"
    assert "password" not in body["user"]
    assert "password_hash" not in body["user"]


def test_register_rejects_duplicate_email(client, professor):
    response = client.post("/api/auth/register", json={
        "email": "prof@university.edu", "name": "Impostor",
        "password": "another-password",
    })
    assert response.status_code == 409


@pytest.mark.parametrize("payload,field", [
    ({"email": "not-an-email", "name": "X", "password": "longenough1"}, "email"),
    ({"email": "a@b.co", "name": "X", "password": "short"}, "password"),
    ({"email": "a@b.co", "name": "", "password": "longenough1"}, "name"),
    ({"email": "a@b.co", "name": "X", "password": "x" * 100}, "password"),
])
def test_register_validation(client, payload, field):
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 422
    assert any(field in p["field"] for p in response.json()["problems"])


def test_login_with_form(client, professor):
    response = client.post("/api/auth/login", data={
        "username": "prof@university.edu", "password": "correct-horse-battery",
    })
    assert response.status_code == 200
    assert response.json()["access_token"]


def test_login_with_json(client, professor):
    response = client.post("/api/auth/login-json", json={
        "email": "prof@university.edu", "password": "correct-horse-battery",
    })
    assert response.status_code == 200


def test_login_wrong_password_is_401(client, professor):
    response = client.post("/api/auth/login", data={
        "username": "prof@university.edu", "password": "wrong",
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_login_unknown_user_gives_the_same_message(client):
    """Different messages would let anyone enumerate accounts."""
    response = client.post("/api/auth/login", data={
        "username": "nobody@nowhere.edu", "password": "whatever",
    })
    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"


def test_me_returns_the_current_user(client, professor):
    response = client.get("/api/auth/me", headers=professor["headers"])
    assert response.status_code == 200
    assert response.json()["email"] == "prof@university.edu"


@pytest.mark.parametrize("headers", [
    {},
    {"Authorization": "Bearer not-a-real-token"},
    {"Authorization": "Basic abc"},
])
def test_protected_routes_require_a_valid_token(client, headers):
    response = client.get("/api/courses", headers=headers)
    assert response.status_code == 401


# ---------------------------------------------------------------------
# Courses
# ---------------------------------------------------------------------
def test_course_crud(client, professor):
    created = client.post("/api/courses", json={
        "name": "CS 106A", "term": "Spring 2026",
    }, headers=professor["headers"])
    assert created.status_code == 201
    course_id = created.json()["id"]
    assert created.json()["assignment_count"] == 0

    listed = client.get("/api/courses", headers=professor["headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    fetched = client.get(f"/api/courses/{course_id}", headers=professor["headers"])
    assert fetched.status_code == 200

    patched = client.patch(f"/api/courses/{course_id}",
                           json={"term": "Fall 2026"},
                           headers=professor["headers"])
    assert patched.status_code == 200
    assert patched.json()["term"] == "Fall 2026"
    assert patched.json()["name"] == "CS 106A", "unset fields must not change"

    deleted = client.delete(f"/api/courses/{course_id}",
                            headers=professor["headers"])
    assert deleted.status_code == 204
    assert client.get(f"/api/courses/{course_id}",
                      headers=professor["headers"]).status_code == 404


def test_empty_patch_is_rejected(client, professor, course):
    response = client.patch(f"/api/courses/{course['id']}", json={},
                            headers=professor["headers"])
    assert response.status_code == 400


def test_a_user_cannot_see_another_users_course(client, professor, course, ta):
    """Ownership isolation - and a 404, not a 403, so nothing leaks."""
    response = client.get(f"/api/courses/{course['id']}", headers=ta["headers"])
    assert response.status_code == 404

    listed = client.get("/api/courses", headers=ta["headers"])
    assert listed.json() == []


def test_ta_cannot_delete_a_course(client, ta):
    """A TA may own a course but not delete one - professors only."""
    created = client.post("/api/courses", json={"name": "TA course"},
                          headers=ta["headers"])
    course_id = created.json()["id"]
    response = client.delete(f"/api/courses/{course_id}", headers=ta["headers"])
    assert response.status_code == 403


# ---------------------------------------------------------------------
# Assignments and rubrics
# ---------------------------------------------------------------------
def test_create_assignment_with_explicit_rubric(client, professor, course):
    response = client.post("/api/assignments", json={
        "course_id": course["id"], "name": "HW1",
        "rubric_json": SIMPLE_RUBRIC,
    }, headers=professor["headers"])

    assert response.status_code == 201
    body = response.json()
    assert body["total_possible_points"] == 100.0
    assert len(body["rubric_json"]["criteria"]) == 3


def test_create_assignment_without_a_rubric_gets_the_default(
    client, professor, course
):
    response = client.post("/api/assignments", json={
        "course_id": course["id"], "name": "HW1",
        "total_possible_points": 50,
    }, headers=professor["headers"])

    assert response.status_code == 201
    rubric = response.json()["rubric_json"]
    assert rubric["total_points"] == 50.0
    assert len(rubric["criteria"]) == 4


def test_create_assignment_from_prose_calls_the_ai(
    client, professor, course, mock_claude
):
    mock_claude({
        "title": "HW1", "total_points": 100, "grading_notes": "",
        "criteria": [{"id": "a", "name": "Everything", "description": "All of it",
                      "max_points": 100, "keywords": [], "requires_output": False}],
    })
    response = client.post("/api/assignments", json={
        "course_id": course["id"], "name": "HW1",
        "rubric_raw_text": "Write a program that sorts a list and explain it.",
    }, headers=professor["headers"])

    assert response.status_code == 201
    assert response.json()["rubric_json"]["criteria"][0]["id"] == "a"


def test_create_assignment_rejects_both_rubric_sources(client, professor, course):
    response = client.post("/api/assignments", json={
        "course_id": course["id"], "name": "HW1",
        "rubric_json": SIMPLE_RUBRIC, "rubric_raw_text": "also prose",
    }, headers=professor["headers"])
    assert response.status_code == 422


def test_create_assignment_rejects_an_invalid_rubric(client, professor, course):
    response = client.post("/api/assignments", json={
        "course_id": course["id"], "name": "HW1",
        "rubric_json": {"criteria": [{"name": "A"}]},   # no max_points
    }, headers=professor["headers"])
    assert response.status_code == 422
    assert "max_points" in response.json()["detail"]


def test_create_assignment_in_someone_elses_course_is_404(client, ta, course):
    response = client.post("/api/assignments", json={
        "course_id": course["id"], "name": "HW1",
    }, headers=ta["headers"])
    assert response.status_code == 404


def test_grading_without_an_api_key_returns_503(client, professor, course):
    """The rubric-extraction path with no key must not be a 500."""
    response = client.post("/api/assignments", json={
        "course_id": course["id"], "name": "HW1",
        "rubric_raw_text": "Some prose that needs the AI to interpret.",
    }, headers=professor["headers"])
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]


def test_rubric_from_solution_builds_a_rubric(client, professor, mock_claude):
    mock_claude({
        "title": "From solution", "total_points": 100, "grading_notes": "",
        "criteria": [
            {"id": "load", "name": "Load data",
             "description": "Reads the dataset.", "max_points": 40,
             "keywords": ["read_csv"], "requires_output": True},
            {"id": "model", "name": "Model",
             "description": "Trains the model.", "max_points": 60,
             "keywords": [], "requires_output": False},
        ],
    })
    data = (SAMPLES / "good_submission.ipynb").read_bytes()
    response = client.post(
        "/api/assignments/rubric/from-solution",
        files={"file": ("solution.ipynb", data, "application/octet-stream")},
        data={"total_points": "100"},
        headers=professor["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_points"] == 100
    assert [c["id"] for c in body["criteria"]] == ["load", "model"]


def test_rubric_from_solution_rejects_a_bad_file_type(client, professor):
    response = client.post(
        "/api/assignments/rubric/from-solution",
        files={"file": ("notes.txt", b"hello", "text/plain")},
        data={"total_points": "100"},
        headers=professor["headers"],
    )
    assert response.status_code == 415


def test_get_rubric(client, professor, assignment):
    response = client.get(f"/api/assignments/{assignment['id']}/rubric",
                          headers=professor["headers"])
    assert response.status_code == 200
    assert response.json()["total_points"] == 100.0


def test_rubric_preview_does_not_save(client, professor, mock_claude):
    mock_claude({
        "title": "Preview", "total_points": 20, "grading_notes": "",
        "criteria": [{"id": "x", "name": "X", "description": "d",
                      "max_points": 20, "keywords": [], "requires_output": False}],
    })
    response = client.post("/api/assignments/rubric/preview", json={
        "text": "Implement quicksort and analyse its complexity.",
        "total_points": 20,
    }, headers=professor["headers"])

    assert response.status_code == 200
    assert response.json()["total_points"] == 20.0
    # nothing was created
    assert client.get("/api/assignments",
                      headers=professor["headers"]).json() == []


def test_update_assignment_revalidates_the_rubric(client, professor, assignment):
    good = client.patch(f"/api/assignments/{assignment['id']}", json={
        "rubric_json": {"criteria": [{"name": "Only", "max_points": 75}]},
    }, headers=professor["headers"])
    assert good.status_code == 200
    assert good.json()["total_possible_points"] == 75.0

    bad = client.patch(f"/api/assignments/{assignment['id']}", json={
        "rubric_json": {"criteria": []},
    }, headers=professor["headers"])
    assert bad.status_code == 422


def test_list_assignments_filters_by_course(client, professor, course, assignment):
    other = client.post("/api/courses", json={"name": "Other course"},
                        headers=professor["headers"]).json()
    client.post("/api/assignments", json={
        "course_id": other["id"], "name": "Other HW",
    }, headers=professor["headers"])

    everything = client.get("/api/assignments", headers=professor["headers"])
    assert len(everything.json()) == 2

    narrowed = client.get(f"/api/assignments?course_id={course['id']}",
                          headers=professor["headers"])
    assert len(narrowed.json()) == 1
    assert narrowed.json()[0]["id"] == assignment["id"]


# ---------------------------------------------------------------------
# Submissions
# ---------------------------------------------------------------------
def test_upload_submissions(client, professor, assignment):
    response = upload_sample(
        client, assignment["id"], professor["headers"],
        "good_submission.ipynb", "good_submission.py",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["uploaded"] == 2
    assert body["failed"] == 0
    assert all(r["ok"] for r in body["results"])
    # the student name is guessed from the filename
    assert body["results"][0]["student_name"] == "Good Submission"


def test_upload_a_zip_creates_a_submission_per_file(client, professor, assignment):
    """A .zip (e.g. Canvas download) becomes one submission per file inside."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("alice_chen_hw3.py",
                         (SAMPLES / "good_submission.py").read_bytes())
        archive.writestr("submissions/bob_smith_hw3.html",
                         (SAMPLES / "good_submission.html").read_bytes())
        archive.writestr("notes.txt", b"ignore me - unsupported")
        archive.writestr("__MACOSX/._junk.py", b"x = 1")   # junk, skipped

    response = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        files=[("files", ("submissions.zip", buf.getvalue(), "application/zip"))],
        headers=professor["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["uploaded"] == 2
    ok_names = {r["filename"] for r in body["results"] if r["ok"]}
    assert ok_names == {"alice_chen_hw3.py", "bob_smith_hw3.html"}


def test_upload_a_zip_with_no_gradeable_files_is_reported(client, professor, assignment):
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        archive.writestr("readme.txt", b"nothing gradeable here")

    response = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        files=[("files", ("empty.zip", buf.getvalue(), "application/zip"))],
        headers=professor["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["uploaded"] == 0
    assert body["failed"] == 1
    assert "no .ipynb" in body["results"][0]["error"]


def test_upload_rejects_unsupported_types_without_failing_the_batch(
    client, professor, assignment
):
    files = [
        ("files", ("good.ipynb", (SAMPLES / "good_submission.ipynb").read_bytes(),
                   "application/json")),
        ("files", ("notes.txt", b"just some text", "text/plain")),
        ("files", ("image.png", b"\x89PNG\r\n", "image/png")),
    ]
    response = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        files=files, headers=professor["headers"],
    )
    assert response.status_code == 201
    body = response.json()
    assert body["uploaded"] == 1
    assert body["failed"] == 2
    failures = [r for r in body["results"] if not r["ok"]]
    assert all("not a supported submission type" in r["error"] for r in failures)


def test_upload_rejects_empty_files(client, professor, assignment):
    files = [("files", ("empty.py", b"", "text/plain"))]
    response = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        files=files, headers=professor["headers"],
    )
    assert response.json()["failed"] == 1
    assert "empty" in response.json()["results"][0]["error"]


def test_upload_rejects_oversize_files(client, professor, assignment, monkeypatch):
    from backend.config import settings
    monkeypatch.setattr(settings, "max_file_size_mb", 0.001)  # ~1 KB

    files = [("files", ("big.py", b"x = 1\n" * 5000, "text/plain"))]
    response = client.post(
        f"/api/assignments/{assignment['id']}/submissions",
        files=files, headers=professor["headers"],
    )
    assert response.json()["failed"] == 1
    assert "exceeds" in response.json()["results"][0]["error"]


def test_list_and_correct_a_submission(client, professor, assignment):
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.ipynb")
    submission_id = upload.json()["results"][0]["submission_id"]

    listed = client.get(f"/api/assignments/{assignment['id']}/submissions",
                        headers=professor["headers"])
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patched = client.patch(f"/api/submissions/{submission_id}", json={
        "student_name": "Alice Chen", "student_email": "alice@university.edu",
    }, headers=professor["headers"])
    assert patched.status_code == 200
    assert patched.json()["student_name"] == "Alice Chen"


def test_delete_a_submission(client, professor, assignment):
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.py")
    submission_id = upload.json()["results"][0]["submission_id"]

    assert client.delete(f"/api/submissions/{submission_id}",
                         headers=professor["headers"]).status_code == 204
    assert client.get(f"/api/submissions/{submission_id}",
                      headers=professor["headers"]).status_code == 404


def test_submissions_are_isolated_between_users(client, professor, assignment, ta):
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.py")
    submission_id = upload.json()["results"][0]["submission_id"]

    assert client.get(f"/api/submissions/{submission_id}",
                      headers=ta["headers"]).status_code == 404
    assert client.delete(f"/api/submissions/{submission_id}",
                         headers=ta["headers"]).status_code == 404


# ---------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------
def test_grade_endpoint(client, professor, assignment, mock_claude, db_session):
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb", "good_submission.py")

    response = grade_now(client, db_session, assignment["id"], professor["headers"])
    body = response
    assert body["graded"] == 2
    assert body["failed"] == 0
    assert all(r["ok"] and r["total_score"] == 89.0 for r in body["results"])


def test_grade_skips_already_graded_unless_regrading(
    client, professor, assignment, mock_claude
, db_session):
    fake = mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")

    grade_now(client, db_session, assignment["id"], professor["headers"])
    assert len(fake.calls) == 1

    again = grade_now(client, db_session, assignment["id"], professor["headers"])
    assert again["skipped"] == 1
    assert len(fake.calls) == 1, "no second API call without regrade=true"

    regrade = grade_now(client, db_session, assignment["id"], professor["headers"], regrade=True)
    assert regrade["graded"] == 1
    assert len(fake.calls) == 2


def test_one_bad_submission_does_not_stop_the_batch(
    client, professor, assignment, mock_claude
, db_session):
    """The whole point of the per-submission error policy."""
    mock_claude()
    files = [
        ("files", ("good.ipynb", (SAMPLES / "good_submission.ipynb").read_bytes(),
                   "application/json")),
        ("files", ("corrupt.ipynb", (SAMPLES / "corrupt.ipynb").read_bytes(),
                   "application/json")),
    ]
    client.post(f"/api/assignments/{assignment['id']}/submissions",
                files=files, headers=professor["headers"])

    response = grade_now(client, db_session, assignment["id"], professor["headers"])
    body = response
    assert body["graded"] == 1
    assert body["failed"] == 1
    failure = next(r for r in body["results"] if not r["ok"])
    assert "not valid JSON" in failure["error"]


def test_grade_a_subset_by_id(client, professor, assignment, mock_claude, db_session):
    mock_claude()
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.ipynb", "good_submission.py")
    first = upload.json()["results"][0]["submission_id"]

    response = grade_now(client, db_session, assignment["id"], professor["headers"], submission_ids=[first])
    assert response["graded"] == 1


# ---------------------------------------------------------------------
# Results, overrides, finalizing
# ---------------------------------------------------------------------
@pytest.fixture
def graded(client, db_session, professor, assignment, mock_claude):
    """An assignment with one graded submission."""
    mock_claude()
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.ipynb")
    grade_now(client, db_session, assignment["id"], professor["headers"])
    submission_id = upload.json()["results"][0]["submission_id"]
    result = client.get(f"/api/submissions/{submission_id}/result",
                        headers=professor["headers"]).json()
    return {"submission_id": submission_id, "result": result}


def test_list_results(client, professor, assignment, graded):
    response = client.get(f"/api/assignments/{assignment['id']}/results",
                          headers=professor["headers"])
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["total_score"] == 89.0
    assert body[0]["effective_score"] == 89.0
    assert len(body[0]["criteria_results"]) == 3
    # the raw model output is preserved for audit
    assert body[0]["ai_raw_output"] == grading_payload()


def test_result_for_an_ungraded_submission_is_404(client, professor, assignment):
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.py")
    submission_id = upload.json()["results"][0]["submission_id"]
    response = client.get(f"/api/submissions/{submission_id}/result",
                          headers=professor["headers"])
    assert response.status_code == 404


def test_override_recomputes_the_total(client, professor, graded):
    grade_id = graded["result"]["id"]
    response = client.patch(f"/api/results/{grade_id}/override", json={
        "overrides": {"model": {"new_score": 45, "note": "Full marks, I was harsh."}},
    }, headers=professor["headers"])

    assert response.status_code == 200
    body = response.json()
    # 27 + 45 + 22 = 94, up from 89
    assert body["effective_score"] == 94.0
    assert body["percentage"] == 94.0
    assert body["letter_grade"] == "A"
    assert body["professor_overrides"]["model"]["new_score"] == 45.0
    # the AI's own scores are untouched
    ai_model = next(c for c in body["criteria_results"]
                    if c["criterion_id"] == "model")
    assert ai_model["score"] == 40.0


def test_override_rejects_an_unknown_criterion(client, professor, graded):
    response = client.patch(f"/api/results/{graded['result']['id']}/override",
                            json={"overrides": {"nope": {"new_score": 10}}},
                            headers=professor["headers"])
    assert response.status_code == 422
    assert "Unknown criterion" in response.json()["detail"]


def test_override_rejects_a_score_above_the_maximum(client, professor, graded):
    response = client.patch(f"/api/results/{graded['result']['id']}/override",
                            json={"overrides": {"model": {"new_score": 999}}},
                            headers=professor["headers"])
    assert response.status_code == 422
    assert "caps at" in response.json()["detail"]


def test_finalize_then_override_is_blocked(client, professor, graded):
    grade_id = graded["result"]["id"]

    finalized = client.post(f"/api/results/{grade_id}/finalize",
                            json={"finalized": True},
                            headers=professor["headers"])
    assert finalized.status_code == 200
    assert finalized.json()["finalized"] is True
    assert finalized.json()["finalized_at"]

    blocked = client.patch(f"/api/results/{grade_id}/override",
                           json={"overrides": {"model": {"new_score": 45}}},
                           headers=professor["headers"])
    assert blocked.status_code == 409

    # un-finalize, then it works again
    client.post(f"/api/results/{grade_id}/finalize", json={"finalized": False},
                headers=professor["headers"])
    assert client.patch(f"/api/results/{grade_id}/override",
                        json={"overrides": {"model": {"new_score": 45}}},
                        headers=professor["headers"]).status_code == 200


def test_ta_cannot_finalize(client, ta, graded):
    """A TA can grade but not approve - that is the whole role split."""
    response = client.post(f"/api/results/{graded['result']['id']}/finalize",
                           json={"finalized": True}, headers=ta["headers"])
    # 404 because the TA does not own the course at all
    assert response.status_code in (403, 404)


def test_stats_endpoint(client, professor, assignment, graded):
    response = client.get(f"/api/assignments/{assignment['id']}/stats",
                          headers=professor["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["total_submissions"] == 1
    assert body["graded"] == 1
    assert body["mean_percentage"] == 89.0
    assert body["grade_distribution"] == {"B+": 1}


# ---------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------
def test_similarity_scan_flags_the_copy(client, professor, assignment):
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.py", "plagiarised.py", "different.py")

    response = client.post(f"/api/assignments/{assignment['id']}/similarity",
                           json={"threshold": 0.5}, headers=professor["headers"])
    assert response.status_code == 200
    flags = response.json()
    assert len(flags) == 1
    assert flags[0]["severity"] == "high"
    assert flags[0]["similarity_score"] >= 0.85
    assert flags[0]["student_a_name"] and flags[0]["student_b_name"]


def test_similarity_review_is_preserved_across_rescans(
    client, professor, assignment
):
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.py", "plagiarised.py")
    flags = client.post(f"/api/assignments/{assignment['id']}/similarity",
                        json={}, headers=professor["headers"]).json()
    flag_id = flags[0]["id"]

    reviewed = client.patch(f"/api/similarity/{flag_id}", json={
        "reviewed": True, "professor_note": "Spoke to both students.",
    }, headers=professor["headers"])
    assert reviewed.status_code == 200
    assert reviewed.json()["reviewed"] is True

    # rescanning must not wipe or duplicate the reviewed flag
    client.post(f"/api/assignments/{assignment['id']}/similarity",
                json={"clear_existing": True}, headers=professor["headers"])
    after = client.get(f"/api/assignments/{assignment['id']}/similarity",
                       headers=professor["headers"]).json()
    assert len(after) == 1
    assert after[0]["reviewed"] is True
    assert after[0]["professor_note"] == "Spoke to both students."


def test_similarity_flag_of_another_user_is_404(client, professor, assignment, ta):
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.py", "plagiarised.py")
    flags = client.post(f"/api/assignments/{assignment['id']}/similarity",
                        json={}, headers=professor["headers"]).json()
    response = client.patch(f"/api/similarity/{flags[0]['id']}",
                            json={"reviewed": True}, headers=ta["headers"])
    assert response.status_code == 404


# ---------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------
@pytest.mark.parametrize("fmt,magic", [
    ("csv", b"student_name"),
    ("canvas_csv", b"Student,ID"),
    ("xlsx", b"PK"),          # zip container
    ("pdf", b"%PDF"),
])
def test_export_formats(client, professor, assignment, graded, fmt, magic):
    response = client.get(
        f"/api/assignments/{assignment['id']}/export?format={fmt}",
        headers=professor["headers"],
    )
    assert response.status_code == 200
    assert magic in response.content[:2000]
    assert "attachment" in response.headers["content-disposition"]


def test_export_rejects_an_unknown_format(client, professor, assignment):
    response = client.get(
        f"/api/assignments/{assignment['id']}/export?format=parquet",
        headers=professor["headers"],
    )
    assert response.status_code == 400
    assert "Unknown export format" in response.json()["detail"]


def test_export_only_finalized(client, professor, assignment, graded):
    before = client.get(
        f"/api/assignments/{assignment['id']}/export"
        f"?format=csv&only_finalized=true",
        headers=professor["headers"],
    )
    # header row only
    assert len(before.content.decode("utf-8-sig").strip().splitlines()) == 1

    client.post(f"/api/results/{graded['result']['id']}/finalize",
                json={"finalized": True}, headers=professor["headers"])

    after = client.get(
        f"/api/assignments/{assignment['id']}/export"
        f"?format=csv&only_finalized=true",
        headers=professor["headers"],
    )
    assert len(after.content.decode("utf-8-sig").strip().splitlines()) == 2


def test_export_of_an_empty_assignment_still_works(client, professor, assignment):
    for fmt in ("csv", "canvas_csv", "xlsx", "pdf"):
        response = client.get(
            f"/api/assignments/{assignment['id']}/export?format={fmt}",
            headers=professor["headers"],
        )
        assert response.status_code == 200, fmt
        assert response.content


# ---------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------
def test_canvas_status_reports_unconfigured(client, professor):
    response = client.get("/api/canvas/status", headers=professor["headers"])
    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_canvas_endpoints_return_501_when_unconfigured(client, professor):
    response = client.get("/api/canvas/courses", headers=professor["headers"])
    assert response.status_code == 501
    detail = response.json()["detail"]
    # The message must point at both ways to fix it: the per-instructor
    # connection in the UI, and the server-wide fallback in .env.
    assert "not connected" in detail
    assert "Settings" in detail and "CANVAS_BASE_URL" in detail


def test_canvas_push_requires_ids(client, professor, assignment, graded):
    response = client.post(
        f"/api/assignments/{assignment['id']}/canvas/push-grades",
        headers=professor["headers"],
    )
    assert response.status_code == 400
    assert "canvas_course_id" in response.json()["detail"]
