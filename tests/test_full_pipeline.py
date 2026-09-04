"""End-to-end pipeline tests - Stage 10.

These walk the workflow a professor actually performs, start to finish,
through the HTTP API. Where the unit tests prove each piece works, these
prove the pieces fit together and that state is consistent at every step.
"""
from __future__ import annotations

import csv
import io

import pytest

from tests.conftest import (
    SAMPLES, SIMPLE_RUBRIC, grade_now, grading_payload, upload_sample,
)


def test_the_whole_workflow(client, professor, mock_claude, db_session):
    """
    Register -> course -> assignment -> upload -> grade -> review ->
    override -> finalize -> similarity scan -> export.
    """
    headers = professor["headers"]
    fake = mock_claude()

    # --- 1. Create a course --------------------------------------------
    course = client.post("/api/courses", json={
        "name": "CS 229 Machine Learning", "term": "Fall 2025",
    }, headers=headers).json()

    # --- 2. Create an assignment with a rubric -------------------------
    assignment = client.post("/api/assignments", json={
        "course_id": course["id"],
        "name": "HW3 - Linear Regression",
        "description": "Fit a linear model to the housing data.",
        "rubric_json": SIMPLE_RUBRIC,
    }, headers=headers).json()

    assert assignment["status"] == "pending"
    assert assignment["submission_count"] == 0
    assert assignment["total_possible_points"] == 100.0

    # --- 3. Upload a realistic mixed batch -----------------------------
    upload = upload_sample(
        client, assignment["id"], headers,
        "good_submission.ipynb",     # complete, executed
        "good_submission.html",      # nbconvert export
        "good_submission.py",        # plain python
        "plagiarised.py",            # rename-only copy of the .py
        "different.py",              # genuinely different approach
        "unrun_submission.ipynb",    # never executed
        "error_submission.ipynb",    # runtime error recorded
        "corrupt.ipynb",             # unparseable
    )
    body = upload.json()
    assert body["uploaded"] == 8, "even the corrupt file uploads; it fails at parse"
    assert body["failed"] == 0

    # --- 4. Grade the batch --------------------------------------------
    grading = grade_now(client, db_session, assignment["id"], headers)

    assert grading["graded"] == 7
    assert grading["failed"] == 1, "the corrupt notebook must fail alone"
    assert grading["skipped"] == 0
    failure = next(r for r in grading["results"] if not r["ok"])
    assert "not valid JSON" in failure["error"]

    # one API call per successfully graded submission
    assert len(fake.calls) == 7

    # --- 5. The assignment reflects the run ----------------------------
    refreshed = client.get(f"/api/assignments/{assignment['id']}",
                           headers=headers).json()
    assert refreshed["submission_count"] == 8
    assert refreshed["graded_count"] >= 1

    # --- 6. Deterministic flags survived the model ---------------------
    results = client.get(f"/api/assignments/{assignment['id']}/results",
                         headers=headers).json()
    assert len(results) == 7

    by_file = {r["original_filename"]: r for r in results}
    assert "no_outputs" in by_file["unrun_submission.ipynb"]["flags"]
    assert "runtime_error" in by_file["error_submission.ipynb"]["flags"]
    assert by_file["good_submission.ipynb"]["flags"] == []

    # --- 7. Stats -------------------------------------------------------
    stats = client.get(f"/api/assignments/{assignment['id']}/stats",
                       headers=headers).json()
    assert stats["total_submissions"] == 8
    assert stats["graded"] == 7
    assert stats["errored"] == 1
    assert stats["mean_percentage"] == 89.0
    assert stats["finalized"] == 0

    # --- 8. Override a score --------------------------------------------
    target = by_file["good_submission.ipynb"]
    overridden = client.patch(f"/api/results/{target['id']}/override", json={
        "overrides": {"writeup": {"new_score": 25, "note": "Better than I first read."}},
        "summary_feedback": "Excellent work, Alice.",
    }, headers=headers).json()

    assert overridden["effective_score"] == 92.0     # 27 + 40 + 25
    assert overridden["letter_grade"] == "A-"
    assert overridden["summary_feedback"] == "Excellent work, Alice."
    # the model's original judgement is intact
    original_writeup = next(c for c in overridden["criteria_results"]
                            if c["criterion_id"] == "writeup")
    assert original_writeup["score"] == 22.0

    # --- 9. Finalize -----------------------------------------------------
    finalized = client.post(f"/api/results/{target['id']}/finalize",
                            json={"finalized": True}, headers=headers).json()
    assert finalized["finalized"] is True

    stats = client.get(f"/api/assignments/{assignment['id']}/stats",
                       headers=headers).json()
    assert stats["finalized"] == 1

    # --- 10. Similarity scan ---------------------------------------------
    flags = client.post(f"/api/assignments/{assignment['id']}/similarity",
                        json={"threshold": 0.6}, headers=headers).json()

    assert len(flags) == 1, "only the rename-only copy should be flagged"
    flagged_names = {flags[0]["student_a_name"], flags[0]["student_b_name"]}
    assert flagged_names == {"Good Submission", "Plagiarised"}
    assert flags[0]["severity"] == "high"

    # --- 11. Export --------------------------------------------------------
    csv_bytes = client.get(
        f"/api/assignments/{assignment['id']}/export?format=csv",
        headers=headers,
    ).content
    rows = list(csv.DictReader(io.StringIO(csv_bytes.decode("utf-8-sig"))))

    assert len(rows) == 8, "every submission appears, graded or not"
    graded_rows = [r for r in rows if r["score"]]
    assert len(graded_rows) == 7
    # the override is what gets exported, not the raw AI score
    alice = next(r for r in rows if r["filename"] == "good_submission.ipynb")
    assert float(alice["score"]) == 92.0
    assert alice["finalized"] == "True"

    # the corrupt one is visible as an error, not silently missing
    corrupt = next(r for r in rows if r["filename"] == "corrupt.ipynb")
    assert corrupt["status"] == "error"
    assert corrupt["score"] == ""

    # --- 12. Other export formats hold together ---------------------------
    for fmt in ("canvas_csv", "xlsx", "pdf"):
        response = client.get(
            f"/api/assignments/{assignment['id']}/export?format={fmt}",
            headers=headers,
        )
        assert response.status_code == 200, fmt
        assert len(response.content) > 100, fmt


def test_parsed_content_is_cached_and_reused(
    client, professor, assignment, mock_claude
, db_session):
    """A regrade must not re-parse - that is what parsed_content is for."""
    fake = mock_claude()
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.ipynb")
    submission_id = upload.json()["results"][0]["submission_id"]

    before = client.get(f"/api/submissions/{submission_id}",
                        headers=professor["headers"]).json()
    assert before["parsed_content"] is None

    grade_now(client, db_session, assignment["id"], professor["headers"])

    after = client.get(f"/api/submissions/{submission_id}",
                       headers=professor["headers"]).json()
    assert after["parsed_content"] is not None
    assert after["parsed_content"]["stats"]["n_code_cells"] == 4
    assert after["status"] == "graded"
    assert after["graded_at"]


def test_regrade_invalidates_a_previous_approval(
    client, professor, assignment, mock_claude
, db_session):
    """A regraded result must not stay marked as approved."""
    fake = mock_claude()
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.ipynb")
    submission_id = upload.json()["results"][0]["submission_id"]

    grade_now(client, db_session, assignment["id"], professor["headers"])
    result = client.get(f"/api/submissions/{submission_id}/result",
                        headers=professor["headers"]).json()
    client.post(f"/api/results/{result['id']}/finalize", json={"finalized": True},
                headers=professor["headers"])

    grade_now(client, db_session, assignment["id"], professor["headers"], regrade=True)

    after = client.get(f"/api/submissions/{submission_id}/result",
                       headers=professor["headers"]).json()
    assert after["finalized"] is False
    assert after["finalized_at"] is None


def test_deleting_an_assignment_removes_its_files_and_rows(
    client, professor, assignment, mock_claude, db_session
):
    from pathlib import Path

    from backend.models.grade_result import GradeResult
    from backend.models.submission import Submission

    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb", "good_submission.py")
    grade_now(client, db_session, assignment["id"], professor["headers"])

    paths = [Path(s.file_path) for s in db_session.query(Submission).all()]
    assert paths and all(p.exists() for p in paths)
    assert db_session.query(GradeResult).count() == 2

    assert client.delete(f"/api/assignments/{assignment['id']}",
                         headers=professor["headers"]).status_code == 204

    assert not any(p.exists() for p in paths), "uploaded files must be removed"
    assert db_session.query(Submission).count() == 0, "submissions must cascade"
    assert db_session.query(GradeResult).count() == 0, "grades must cascade"


def test_grading_continues_after_an_api_failure_mid_batch(
    client, professor, assignment, mock_claude
, db_session):
    """
    An API error on one submission must not lose the ones already graded
    or block the ones after it.
    """
    import anthropic
    import httpx

    fake = mock_claude()
    upload = upload_sample(client, assignment["id"], professor["headers"],
                           "good_submission.ipynb", "good_submission.py",
                           "different.py")

    # Grade the first one normally.
    first = upload.json()["results"][0]["submission_id"]
    grade_now(client, db_session, assignment["id"], professor["headers"], submission_ids=[first])

    # Now make every further call fail.
    fake.raises = anthropic.RateLimitError(
        "429",
        response=httpx.Response(
            429, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
        ),
        body=None,
    )

    outcome = grade_now(client, db_session, assignment["id"], professor["headers"])

    assert outcome["skipped"] == 1, "the already-graded one is left alone"
    assert outcome["failed"] == 2
    assert all("rate limit" in r["error"] for r in outcome["results"] if not r["ok"])

    # The successful grade survived the failed batch.
    results = client.get(f"/api/assignments/{assignment['id']}/results",
                         headers=professor["headers"]).json()
    assert len(results) == 1
    assert results[0]["total_score"] == 89.0

    # The failed submissions are marked, with the reason recorded.
    submissions = client.get(f"/api/assignments/{assignment['id']}/submissions",
                             headers=professor["headers"]).json()
    errored = [s for s in submissions if s["status"] == "error"]
    assert len(errored) == 2
    assert all(s["error_message"] for s in errored)


def test_a_second_professor_sees_none_of_the_first_ones_data(
    client, professor, assignment, mock_claude
, db_session):
    """Full-stack ownership isolation, not just per-endpoint."""
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    grade_now(client, db_session, assignment["id"], professor["headers"])

    other = client.post("/api/auth/register", json={
        "email": "other@university.edu", "name": "Other Prof",
        "password": "a-different-password",
    }).json()
    other_headers = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.get("/api/courses", headers=other_headers).json() == []
    assert client.get("/api/assignments", headers=other_headers).json() == []

    for path in (
        f"/api/assignments/{assignment['id']}",
        f"/api/assignments/{assignment['id']}/results",
        f"/api/assignments/{assignment['id']}/stats",
        f"/api/assignments/{assignment['id']}/submissions",
        f"/api/assignments/{assignment['id']}/export?format=csv",
    ):
        assert client.get(path, headers=other_headers).status_code == 404, path

    assert client.post(f"/api/assignments/{assignment['id']}/grade",
                       json={}, headers=other_headers).status_code == 404


def test_html_and_notebook_of_the_same_work_both_grade(
    client, professor, assignment, mock_claude
, db_session):
    """Format must not change whether a submission is gradeable."""
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb", "good_submission.html",
                  "classic_submission.html", "generic.html")

    outcome = grade_now(client, db_session, assignment["id"], professor["headers"])
    assert outcome["graded"] == 4
    assert outcome["failed"] == 0
