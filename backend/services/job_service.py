"""
Durable grading jobs.

This module owns the queue. The API writes a job and returns; a worker
claims it, runs it, and reports progress; the UI polls. Nothing holds an
HTTP request open for the length of a grading run any more.

Claiming is transactional. On PostgreSQL a candidate row is locked with
`SELECT ... FOR UPDATE SKIP LOCKED`, so several workers can pull from the
same queue without ever handing the same job to two of them and without
blocking each other on a contended row. SQLite has no `SKIP LOCKED`; there
the same guarantee comes from a compare-and-swap update
(`UPDATE ... WHERE id = ? AND status = 'queued'`), which is sufficient
because SQLite serialises writers anyway. Both paths finish with the same
CAS, so a lost race simply claims nothing and the loop tries again.

Crash recovery is by heartbeat, not by timeout on the whole run: a job may
legitimately take an hour, so "is it still alive?" cannot be inferred from
how long it has been going. A worker touches `heartbeat_at` as it works; a
`running` job whose heartbeat has gone stale is assumed dead and is either
retried or failed, depending on how many attempts it has already had.
"""
from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models.assignment import Assignment
from backend.models.grading_job import ACTIVE_STATUSES, GradingJob, JobStatus
from backend.models.submission import Submission
from backend.models.user import User
from backend.services.grading_service import GradingInProgressError, grade_assignment
from backend.utils.logging_utils import log_event

# How long a running job may go without a heartbeat before another worker
# assumes it died. Comfortably longer than one submission takes to grade
# (the model call is capped at settings.llm_timeout_seconds).
HEARTBEAT_TIMEOUT = timedelta(minutes=10)

# Don't write a heartbeat on every single submission - once every few
# seconds is plenty and keeps the write rate off the database.
HEARTBEAT_INTERVAL = timedelta(seconds=20)


def worker_identity() -> str:
    """Something a human can trace back to a container in a log line."""
    return f"{socket.gethostname()}:{os.getpid()}"


# ---------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------
def active_job_for(db: Session, assignment_id: str) -> GradingJob | None:
    """The queued or running job for an assignment, if there is one."""
    return (
        db.query(GradingJob)
        .filter(GradingJob.assignment_id == assignment_id,
                GradingJob.status.in_(ACTIVE_STATUSES))
        .order_by(GradingJob.created_at.desc())
        .first()
    )


def enqueue_grading_job(
    db: Session,
    assignment: Assignment,
    user: User,
    *,
    submission_ids: list[str] | None = None,
    regrade: bool = False,
    include_images: bool = True,
) -> GradingJob:
    """
    Queue a grading run, refusing to queue a second one for the same
    assignment.

    The check below is a courtesy that produces a good error message; the
    guarantee comes from the partial unique index on
    (assignment_id) WHERE status IN ('queued','running'). Two requests that
    race past the check both try to insert and the database rejects one of
    them - which is precisely the double-click case.
    """
    existing = active_job_for(db, assignment.id)
    if existing is not None:
        raise GradingInProgressError(
            "This assignment is already being graded. Wait for that run to "
            "finish, or cancel it, before starting another."
        )

    total = _eligible_count(db, assignment, submission_ids)

    job = GradingJob(
        assignment_id=assignment.id,
        user_id=user.id,
        status=JobStatus.QUEUED,
        params={
            "regrade": bool(regrade),
            "include_images": bool(include_images),
            "submission_ids": list(submission_ids) if submission_ids else None,
        },
        total=total,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise GradingInProgressError(
            "This assignment is already being graded. Wait for that run to "
            "finish, or cancel it, before starting another."
        ) from exc
    db.refresh(job)

    log_event("grading_job.enqueued", job_id=job.id, assignment_id=assignment.id,
              user_id=user.id, total=total, regrade=regrade)
    return job


def _eligible_count(db: Session, assignment: Assignment,
                    submission_ids: list[str] | None) -> int:
    query = db.query(Submission).filter(Submission.assignment_id == assignment.id)
    if submission_ids:
        query = query.filter(Submission.id.in_(submission_ids))
    return query.count()


# ---------------------------------------------------------------------
# Claiming
# ---------------------------------------------------------------------
def claim_next_job(db: Session, worker_id: str) -> GradingJob | None:
    """
    Atomically take ownership of the oldest queued job, or return None.

    Never raises on contention: losing the race means another worker got
    there first, which is a normal outcome, not an error.
    """
    dialect = db.bind.dialect.name if db.bind is not None else "sqlite"

    if dialect == "postgresql":
        row = db.execute(text(
            "SELECT id FROM grading_jobs WHERE status = :queued "
            "ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1"
        ), {"queued": JobStatus.QUEUED}).first()
    else:
        row = db.execute(text(
            "SELECT id FROM grading_jobs WHERE status = :queued "
            "ORDER BY created_at LIMIT 1"
        ), {"queued": JobStatus.QUEUED}).first()

    if row is None:
        db.rollback()
        return None

    now = datetime.utcnow()
    # Compare-and-swap: only claim it if it is still queued.
    claimed = (
        db.query(GradingJob)
        .filter(GradingJob.id == row[0], GradingJob.status == JobStatus.QUEUED)
        .update(
            {
                "status": JobStatus.RUNNING,
                "locked_by": worker_id,
                "heartbeat_at": now,
                "started_at": now,
                "attempts": GradingJob.attempts + 1,
                "updated_at": now,
            },
            synchronize_session=False,
        )
    )
    db.commit()
    if not claimed:
        return None

    job = db.get(GradingJob, row[0])
    log_event("grading_job.claimed", job_id=job.id, worker=worker_id,
              attempt=job.attempts, assignment_id=job.assignment_id)
    return job


# ---------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------
def run_job(db: Session, job: GradingJob, worker_id: str | None = None) -> GradingJob:
    """
    Execute one claimed job to completion, failure, or cancellation.

    Grading behaviour itself is unchanged - this calls the same
    `grade_assignment` the synchronous endpoint used to call. All this adds
    is progress reporting, a heartbeat, and an honest terminal state.
    """
    worker_id = worker_id or job.locked_by or worker_identity()
    assignment = db.get(Assignment, job.assignment_id)
    if assignment is None:
        return _finish(db, job, JobStatus.FAILED,
                       error="The assignment was deleted before grading started.")

    last_beat = datetime.utcnow()

    def on_progress(counters: dict[str, int]) -> None:
        nonlocal last_beat
        job.processed = counters["processed"]
        job.graded = counters["graded"]
        job.failed = counters["failed"]
        job.skipped = counters["skipped"]
        now = datetime.utcnow()
        if now - last_beat >= HEARTBEAT_INTERVAL:
            job.heartbeat_at = now
            last_beat = now
        job.updated_at = now
        db.commit()

    def should_cancel() -> bool:
        # Read the column rather than the identity-mapped object: the
        # cancellation was committed by the API in a different session.
        current = db.query(GradingJob.status).filter(
            GradingJob.id == job.id).scalar()
        return current == JobStatus.CANCELLED

    # Whose key pays for this run: the job's owner if they have chosen
    # their own provider, otherwise the administrator's. Resolved once per
    # job rather than per submission, so a batch cannot switch mid-run.
    from backend.models.user import User
    from backend.services.credential_service import resolve_provider_for_user

    try:
        provider = resolve_provider_for_user(db, db.get(User, job.user_id))
    except Exception as exc:  # noqa: BLE001 - fall back rather than fail a batch
        log_event("grading_job.provider_fallback", level="warning",
                  job_id=job.id, error=type(exc).__name__)
        provider = None

    params = job.params or {}
    try:
        summary = grade_assignment(
            db, assignment,
            provider=provider,
            submission_ids=params.get("submission_ids"),
            regrade=bool(params.get("regrade")),
            include_images=bool(params.get("include_images", True)),
            on_progress=on_progress,
            should_cancel=should_cancel,
        )
    except Exception as exc:  # noqa: BLE001 - the worker must never die on one job
        db.rollback()
        job = db.get(GradingJob, job.id)
        retryable = job.attempts < job.max_attempts
        log_event("grading_job.error", level="error", job_id=job.id,
                  worker=worker_id, attempt=job.attempts,
                  will_retry=retryable, error=type(exc).__name__)
        if retryable:
            # Back into the queue; a later attempt may well succeed if the
            # cause was a provider blip rather than bad data.
            return _finish(db, job, JobStatus.QUEUED, error=str(exc)[:2000])
        return _finish(db, job, JobStatus.FAILED, error=str(exc)[:2000])

    job = db.get(GradingJob, job.id)
    job.results = summary.get("results")
    job.graded = summary.get("graded", job.graded)
    job.failed = summary.get("failed", job.failed)
    job.skipped = summary.get("skipped", job.skipped)
    job.processed = job.graded + job.failed + job.skipped

    if summary.get("cancelled"):
        return _finish(db, job, JobStatus.CANCELLED,
                       error="Cancelled by the professor.")
    return _finish(db, job, JobStatus.COMPLETED)


def _finish(db: Session, job: GradingJob, status: str,
            error: str | None = None) -> GradingJob:
    job.status = status
    job.error_message = error
    job.updated_at = datetime.utcnow()
    if status == JobStatus.QUEUED:
        # A retry: release the claim so another worker can pick it up.
        job.locked_by = None
        job.heartbeat_at = None
        job.started_at = None
    else:
        job.finished_at = datetime.utcnow()
        job.locked_by = None
    db.commit()
    db.refresh(job)
    log_event(f"grading_job.{status}", job_id=job.id,
              assignment_id=job.assignment_id, graded=job.graded,
              failed=job.failed, skipped=job.skipped,
              level="error" if status == JobStatus.FAILED else "info")
    return job


def run_pending_jobs(db: Session, *, worker_id: str | None = None,
                     max_jobs: int = 1) -> int:
    """
    Claim and run up to `max_jobs` queued jobs. Returns how many ran.

    Used by the worker loop and, inline, by the test-suite - so the tests
    exercise the real enqueue/claim/run path rather than a shortcut.
    """
    worker_id = worker_id or worker_identity()
    done = 0
    for _ in range(max_jobs):
        job = claim_next_job(db, worker_id)
        if job is None:
            break
        run_job(db, job, worker_id)
        done += 1
    return done


# ---------------------------------------------------------------------
# Recovery and cancellation
# ---------------------------------------------------------------------
def reap_stale_jobs(db: Session) -> int:
    """
    Requeue (or fail) jobs whose worker stopped heartbeating.

    This is what makes a `docker restart` or an OOM-killed worker
    survivable: the run resumes instead of sitting in `running` forever.
    Already-graded submissions are skipped on the retry, so the work is not
    repeated and the model is not paid twice for it.
    """
    cutoff = datetime.utcnow() - HEARTBEAT_TIMEOUT
    stale = (
        db.query(GradingJob)
        .filter(GradingJob.status == JobStatus.RUNNING,
                GradingJob.heartbeat_at.isnot(None),
                GradingJob.heartbeat_at < cutoff)
        .all()
    )
    # A job claimed but never heartbeated (worker died immediately) has a
    # started_at but no heartbeat; catch those too.
    stale += (
        db.query(GradingJob)
        .filter(GradingJob.status == JobStatus.RUNNING,
                GradingJob.heartbeat_at.is_(None),
                GradingJob.started_at.isnot(None),
                GradingJob.started_at < cutoff)
        .all()
    )

    for job in stale:
        retryable = job.attempts < job.max_attempts
        log_event("grading_job.stale", level="warning", job_id=job.id,
                  worker=job.locked_by, attempt=job.attempts,
                  will_retry=retryable)
        _finish(db, job,
                JobStatus.QUEUED if retryable else JobStatus.FAILED,
                error="The worker running this job stopped responding.")
    return len(stale)


def cancel_job(db: Session, job: GradingJob) -> GradingJob:
    """
    Ask a job to stop.

    A queued job stops immediately. A running job is marked cancelled and
    the worker notices between submissions - it is never killed mid-call,
    so a submission is not left half-written.
    """
    if job.status not in ACTIVE_STATUSES:
        return job
    if job.status == JobStatus.QUEUED:
        return _finish(db, job, JobStatus.CANCELLED,
                       error="Cancelled before it started.")

    job.status = JobStatus.CANCELLED
    job.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(job)
    log_event("grading_job.cancel_requested", job_id=job.id,
              assignment_id=job.assignment_id)
    return job
