"""
The grading worker.

    python -m backend.worker

A deliberately dull loop: reap anything a dead worker left behind, claim one
job, run it, repeat. It is a separate process from the API so that a grading
run - minutes to hours of blocking model calls - cannot occupy an API worker
or be killed by a request timeout.

Scaling is by running more of these. Claiming is transactional
(`FOR UPDATE SKIP LOCKED` on PostgreSQL), so several workers share one queue
safely without any coordination between them.

Shutdown is graceful: SIGTERM sets a flag and the loop finishes the job it is
on before exiting. `docker stop` therefore does not tear a batch in half -
and if the container is killed outright anyway, the heartbeat reaper picks
the job up on the next start.
"""
from __future__ import annotations

import signal
import sys
import time
from types import FrameType

from backend.config import settings
from backend.database import SessionLocal
from backend.services.job_service import (
    reap_stale_jobs, run_pending_jobs, worker_identity,
)
from backend.utils.logging_utils import configure_logging, log_event

# How long to wait before looking for work again when the queue is empty.
IDLE_SLEEP_SECONDS = 5.0

# Checking for abandoned jobs on every pass would be wasted queries; once a
# minute is soon enough to recover from a crash.
REAP_INTERVAL_SECONDS = 60.0

_shutdown = False


def _handle_signal(signum: int, _frame: FrameType | None) -> None:
    global _shutdown
    _shutdown = True
    log_event("worker.shutdown_requested", signal=signum)


def main() -> int:
    configure_logging()
    worker_id = worker_identity()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    log_event("worker.started", worker=worker_id,
              provider=settings.active_provider(),
              database=settings.database_url.split("://", 1)[0])

    last_reap = 0.0
    while not _shutdown:
        try:
            with SessionLocal() as db:
                now = time.monotonic()
                if now - last_reap >= REAP_INTERVAL_SECONDS:
                    reaped = reap_stale_jobs(db)
                    if reaped:
                        log_event("worker.reaped_stale_jobs", count=reaped,
                                  worker=worker_id, level="warning")
                    last_reap = now

                ran = run_pending_jobs(db, worker_id=worker_id, max_jobs=1)

            if not ran:
                # Sleep in short slices so SIGTERM is noticed promptly
                # rather than after a full idle period.
                for _ in range(int(IDLE_SLEEP_SECONDS * 2)):
                    if _shutdown:
                        break
                    time.sleep(0.5)

        except Exception:  # noqa: BLE001 - the loop outlives any one failure
            # A database blip must not end the worker; back off and retry.
            # run_job already converts per-job failures into job state, so
            # reaching here means something outside a job went wrong.
            log_event("worker.loop_error", level="error", worker=worker_id)
            import logging
            logging.getLogger(__name__).exception("Worker loop error")
            time.sleep(IDLE_SLEEP_SECONDS)

    log_event("worker.stopped", worker=worker_id)
    return 0


if __name__ == "__main__":
    sys.exit(main())
