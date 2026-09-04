"""
GradingJob - one durable record of "grade this assignment".

Grading a class takes tens of minutes, which is far too long to hold an HTTP
request open: a proxy timeout, a browser refresh or a container restart used
to lose the whole run along with the model spend it had already incurred.
A job row moves that work off the request path. The API writes a row, a
worker picks it up, and the UI polls a cheap status endpoint.

Two invariants the rest of the system relies on:

* **One active job per assignment.** Enforced by a partial unique index
  (`uq_grading_jobs_active_assignment`), not just by an application check,
  so two simultaneous requests cannot both pass the check and then both
  insert. This is what makes a double-click harmless.
* **Every job has an owner.** `user_id` is the professor who started it, so
  status and cancellation can be authorised without walking back up to the
  course on every poll.
"""
import uuid
from datetime import datetime

from sqlalchemy import (
    Column, DateTime, ForeignKey, Index, Integer, JSON, String, Text,
)
from sqlalchemy.orm import relationship

from backend.database import Base


class JobStatus(str):
    QUEUED    = "queued"      # written, waiting for a worker
    RUNNING   = "running"     # claimed, being graded
    COMPLETED = "completed"   # finished; see counters for what happened
    FAILED    = "failed"      # gave up after max_attempts
    CANCELLED = "cancelled"   # a professor stopped it


# The states that occupy an assignment. A new job may only be enqueued when
# no job for that assignment is in one of these.
ACTIVE_STATUSES = (JobStatus.QUEUED, JobStatus.RUNNING)
TERMINAL_STATUSES = (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED)


class GradingJob(Base):
    __tablename__ = "grading_jobs"

    id            = Column(String(36), primary_key=True,
                           default=lambda: str(uuid.uuid4()))
    assignment_id = Column(String(36), ForeignKey("assignments.id",
                           ondelete="CASCADE"), nullable=False, index=True)
    # The professor who started the run - the owner for authorisation.
    user_id       = Column(String(36), ForeignKey("users.id",
                           ondelete="CASCADE"), nullable=False, index=True)

    status        = Column(String(20), default=JobStatus.QUEUED,
                           nullable=False, index=True)

    # What was asked for: {"regrade": bool, "include_images": bool,
    #                      "submission_ids": [...] | None}
    params        = Column(JSON, nullable=False, default=dict)

    # Progress, updated as the worker goes so the UI can show a real bar
    # rather than a spinner of unknown length.
    total         = Column(Integer, default=0, nullable=False)
    processed     = Column(Integer, default=0, nullable=False)
    graded        = Column(Integer, default=0, nullable=False)
    failed        = Column(Integer, default=0, nullable=False)
    skipped       = Column(Integer, default=0, nullable=False)

    # Per-submission outcome, same shape the synchronous endpoint used to
    # return, so the review UI can list what happened to each student.
    results       = Column(JSON, nullable=True)

    error_message = Column(Text, nullable=True)
    attempts      = Column(Integer, default=0, nullable=False)
    max_attempts  = Column(Integer, default=3, nullable=False)

    # Which worker holds it, and when it last proved it was alive. A running
    # job whose heartbeat has gone stale is assumed dead and is retried.
    locked_by     = Column(String(120), nullable=True)
    heartbeat_at  = Column(DateTime, nullable=True)

    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at    = Column(DateTime, nullable=True)
    finished_at   = Column(DateTime, nullable=True)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    assignment = relationship("Assignment")
    user       = relationship("User")

    __table_args__ = (
        # The duplicate-click guard. A partial index, so completed jobs do
        # not block the next run. Postgres and SQLite (3.8+) both support it.
        Index(
            "uq_grading_jobs_active_assignment",
            "assignment_id",
            unique=True,
            sqlite_where=Column("status").in_(ACTIVE_STATUSES),
            postgresql_where=Column("status").in_(ACTIVE_STATUSES),
        ),
        Index("ix_grading_jobs_status_created", "status", "created_at"),
    )

    @property
    def is_active(self) -> bool:
        return self.status in ACTIVE_STATUSES

    @property
    def progress_percent(self) -> int:
        if not self.total:
            return 0
        return int(round(self.processed / self.total * 100))

    def __repr__(self) -> str:
        return f"<GradingJob {self.id[:8]} {self.status} {self.processed}/{self.total}>"
