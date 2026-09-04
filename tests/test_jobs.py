"""
Grading jobs: persistence, ownership, duplicates, retries, crash recovery.

These cover the failure modes that made synchronous grading fragile. Each
one asks the same question in a different way: if something dies halfway
through an hour of grading, what happens to the work already paid for?
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.orm import sessionmaker

from backend.models.grading_job import GradingJob, JobStatus
from backend.services.job_service import (
    HEARTBEAT_TIMEOUT, claim_next_job, enqueue_grading_job, reap_stale_jobs,
    run_pending_jobs,
)
from tests.conftest import grading_payload, upload_sample


def _second_session(db_session):
    """
    A separate session on the same database.

    Stands in for another process - the worker, or the API after a restart.
    Anything visible here came from the database, not from an identity map.
    """
    return sessionmaker(bind=db_session.get_bind())()


def _enqueue(client, professor, assignment, **params):
    response = client.post(f"/api/assignments/{assignment['id']}/grade",
                           json=params, headers=professor["headers"])
    assert response.status_code == 202, response.text
    return response.json()


# ---------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------
def test_grade_request_returns_immediately_with_a_queued_job(
        client, professor, assignment, mock_claude):
    """The request must not wait for grading - that was the whole problem."""
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")

    job = _enqueue(client, professor, assignment)
    assert job["status"] == JobStatus.QUEUED
    assert job["total"] == 1
    assert job["processed"] == 0


def test_a_queued_job_survives_an_application_restart(
        client, db_session, professor, assignment, mock_claude):
    """
    A restart between enqueue and run must not lose the work. The job is a
    row, so a brand-new session - a new process, in production - finds it
    and runs it.
    """
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    job = _enqueue(client, professor, assignment)

    # Nothing of this job exists in memory in the "restarted" process.
    fresh = _second_session(db_session)
    try:
        assert run_pending_jobs(fresh, worker_id="worker-after-restart") == 1
        reloaded = fresh.get(GradingJob, job["id"])
        assert reloaded.status == JobStatus.COMPLETED
        assert reloaded.graded == 1
    finally:
        fresh.close()


def test_progress_is_recorded_as_the_run_proceeds(
        client, db_session, professor, assignment, mock_claude):
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb", "good_submission.py")
    job = _enqueue(client, professor, assignment)

    run_pending_jobs(db_session, worker_id="w1")
    body = client.get(f"/api/jobs/{job['id']}",
                      headers=professor["headers"]).json()
    assert body["status"] == JobStatus.COMPLETED
    assert body["processed"] == 2
    assert body["graded"] == 2
    assert body["progress_percent"] == 100
    # The per-student breakdown the review page shows.
    assert len(body["results"]) == 2


# ---------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------
def test_a_second_request_while_one_is_queued_is_refused(
        client, professor, assignment, mock_claude):
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    _enqueue(client, professor, assignment)

    again = client.post(f"/api/assignments/{assignment['id']}/grade",
                        json={}, headers=professor["headers"])
    assert again.status_code == 409


def test_the_database_refuses_a_duplicate_even_without_the_check(
        client, db_session, professor, assignment, mock_claude):
    """
    The application check is a courtesy; the guarantee is the partial unique
    index. Two requests that race past the check must not both insert.
    """
    from sqlalchemy.exc import IntegrityError

    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    _enqueue(client, professor, assignment)

    # Bypass enqueue_grading_job entirely and insert straight into the table.
    duplicate = GradingJob(
        assignment_id=assignment["id"], user_id=professor["user"]["id"],
        status=JobStatus.QUEUED, params={}, total=1,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_a_new_run_is_allowed_once_the_previous_one_finished(
        client, db_session, professor, assignment, mock_claude):
    """The index is partial - a completed job must not block the next run."""
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    _enqueue(client, professor, assignment)
    run_pending_jobs(db_session, worker_id="w1")

    second = client.post(f"/api/assignments/{assignment['id']}/grade",
                         json={"regrade": True}, headers=professor["headers"])
    assert second.status_code == 202


# ---------------------------------------------------------------------
# Ownership
# ---------------------------------------------------------------------
def test_another_professor_cannot_see_or_cancel_a_job(
        client, professor, assignment, mock_claude):
    """
    Jobs are course-scoped like everything else, and a stranger gets 404
    rather than 403 - confirming the job exists would leak that the
    assignment does.
    """
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    job = _enqueue(client, professor, assignment)

    other = client.post("/api/auth/register", json={
        "email": "stranger@university.edu", "name": "Stranger",
        "password": "another-good-password", "role": "professor",
    }).json()
    headers = {"Authorization": f"Bearer {other['access_token']}"}

    assert client.get(f"/api/jobs/{job['id']}", headers=headers).status_code == 404
    assert client.post(f"/api/jobs/{job['id']}/cancel",
                       headers=headers).status_code == 404
    assert client.get(f"/api/assignments/{assignment['id']}/jobs/latest",
                      headers=headers).status_code == 404


def test_a_job_requires_authentication(client, professor, assignment, mock_claude):
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    job = _enqueue(client, professor, assignment)
    assert client.get(f"/api/jobs/{job['id']}").status_code == 401


# ---------------------------------------------------------------------
# Claiming
# ---------------------------------------------------------------------
def test_a_job_is_claimed_exactly_once(
        client, db_session, professor, assignment, mock_claude):
    """Two workers must never both pick up the same job."""
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    _enqueue(client, professor, assignment)

    first = claim_next_job(db_session, "worker-a")
    second = claim_next_job(db_session, "worker-b")

    assert first is not None
    assert second is None, "a claimed job was handed out twice"
    assert first.status == JobStatus.RUNNING
    assert first.locked_by == "worker-a"
    assert first.attempts == 1


def test_claiming_an_empty_queue_returns_nothing(db_session):
    assert claim_next_job(db_session, "idle-worker") is None


# ---------------------------------------------------------------------
# Failure, retry, and crash recovery
# ---------------------------------------------------------------------
def test_a_failing_job_is_retried_then_marked_failed(
        client, db_session, professor, assignment, mock_claude, monkeypatch):
    """
    A failure outside any single submission - a database blip, say - should
    be retried, because the same job may well succeed on the next attempt.
    After max_attempts it stops and says so rather than looping forever.
    """
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    job = _enqueue(client, professor, assignment)

    def _explode(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr("backend.services.job_service.grade_assignment", _explode)

    for expected_attempt in (1, 2):
        run_pending_jobs(db_session, worker_id="w1")
        row = db_session.get(GradingJob, job["id"])
        db_session.refresh(row)
        assert row.status == JobStatus.QUEUED, "should go back on the queue"
        assert row.attempts == expected_attempt
        assert row.locked_by is None, "a retryable job must release its claim"

    run_pending_jobs(db_session, worker_id="w1")           # third attempt
    row = db_session.get(GradingJob, job["id"])
    db_session.refresh(row)
    assert row.status == JobStatus.FAILED
    assert row.attempts == 3
    assert "database went away" in row.error_message


def test_a_worker_that_dies_mid_job_has_it_requeued(
        client, db_session, professor, assignment, mock_claude):
    """
    The heartbeat, not a wall-clock timeout, is what detects a dead worker:
    a legitimate run can take an hour, so "it has been going a long time"
    proves nothing. A stale heartbeat does.
    """
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    job_id = _enqueue(client, professor, assignment)["id"]

    claimed = claim_next_job(db_session, "worker-that-will-die")
    assert claimed.id == job_id

    # The worker is killed: no more heartbeats.
    stale = datetime.utcnow() - HEARTBEAT_TIMEOUT - timedelta(minutes=1)
    db_session.query(GradingJob).filter(GradingJob.id == job_id).update(
        {"heartbeat_at": stale}, synchronize_session=False)
    db_session.commit()

    assert reap_stale_jobs(db_session) == 1
    row = db_session.get(GradingJob, job_id)
    db_session.refresh(row)
    assert row.status == JobStatus.QUEUED
    assert row.locked_by is None

    # And a healthy worker finishes the run.
    assert run_pending_jobs(db_session, worker_id="worker-b") == 1
    db_session.refresh(row)
    assert row.status == JobStatus.COMPLETED


def test_a_live_job_is_not_reaped(client, db_session, professor, assignment,
                                  mock_claude):
    """A long but healthy run must be left alone."""
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    _enqueue(client, professor, assignment)
    claim_next_job(db_session, "busy-worker")

    assert reap_stale_jobs(db_session) == 0


def test_work_already_done_is_not_repeated_after_a_crash(
        client, db_session, professor, assignment, mock_claude):
    """
    The point of resuming rather than restarting: a retry must not pay the
    model again for submissions that were already graded.
    """
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb", "good_submission.py")
    fake = mock_claude()

    _enqueue(client, professor, assignment)
    run_pending_jobs(db_session, worker_id="w1")
    calls_after_first_run = len(fake.calls)
    assert calls_after_first_run == 2

    # A second run without regrade skips what is already graded.
    _enqueue(client, professor, assignment)
    run_pending_jobs(db_session, worker_id="w2")
    assert len(fake.calls) == calls_after_first_run, \
        "already-graded submissions were sent to the model again"


# ---------------------------------------------------------------------
# Provider failures
# ---------------------------------------------------------------------
def test_a_provider_timeout_fails_the_submission_not_the_job(
        client, db_session, professor, assignment, mock_claude):
    """
    A provider outage should be recorded per submission and leave the batch
    to continue - one bad call must not throw away the rest of the run.
    """
    import anthropic
    import httpx

    fake = mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    fake.raises = anthropic.APITimeoutError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )

    job_id = _enqueue(client, professor, assignment)["id"]
    run_pending_jobs(db_session, worker_id="w1")

    body = client.get(f"/api/jobs/{job_id}", headers=professor["headers"]).json()
    assert body["status"] == JobStatus.COMPLETED, \
        "a provider failure is a submission outcome, not a job crash"
    assert body["failed"] == 1
    assert body["graded"] == 0


# ---------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------
def test_a_queued_job_can_be_cancelled_before_it_runs(
        client, db_session, professor, assignment, mock_claude):
    fake = mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    job_id = _enqueue(client, professor, assignment)["id"]

    cancelled = client.post(f"/api/jobs/{job_id}/cancel",
                            headers=professor["headers"])
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == JobStatus.CANCELLED

    # A cancelled job is not picked up, and nothing is sent to the model.
    assert run_pending_jobs(db_session, worker_id="w1") == 0
    assert fake.calls == []


def test_cancelling_frees_the_assignment_for_a_new_run(
        client, professor, assignment, mock_claude):
    mock_claude()
    upload_sample(client, assignment["id"], professor["headers"],
                  "good_submission.ipynb")
    job_id = _enqueue(client, professor, assignment)["id"]
    client.post(f"/api/jobs/{job_id}/cancel", headers=professor["headers"])

    assert client.post(f"/api/assignments/{assignment['id']}/grade",
                       json={}, headers=professor["headers"]).status_code == 202


# ---------------------------------------------------------------------
# Database failure
# ---------------------------------------------------------------------
def test_the_worker_loop_survives_a_database_failure(monkeypatch):
    """
    A database blip must not end the worker process - it should log, back
    off, and carry on, because the jobs are still there when it recovers.
    """
    import backend.worker as worker

    calls = {"n": 0}

    def _boom():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("connection refused")
        worker._shutdown = True          # let the loop exit on the next pass
        raise RuntimeError("still down")

    monkeypatch.setattr(worker, "SessionLocal", _boom)
    monkeypatch.setattr(worker.time, "sleep", lambda _s: None)
    monkeypatch.setattr(worker, "_shutdown", False)

    assert worker.main() == 0, "the worker exited instead of riding out the outage"
    assert calls["n"] >= 2
