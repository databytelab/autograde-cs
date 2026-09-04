"""Submission upload, grading kick-off, and similarity scanning."""
from __future__ import annotations

import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from typing import BinaryIO, Iterator

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models.assignment import Assignment
from backend.models.similarity_flag import SimilarityFlag
from backend.models.submission import Submission
from backend.models.user import User
from backend.parsers import parse_submission
from backend.routers.deps import (
    get_owned_assignment,
    get_owned_job,
    get_owned_submission,
)
from backend.schemas.submission import (
    GradeRequest,
    GradeResponse,
    SimilarityFlagDetail,
    SimilarityReviewRequest,
    SimilarityScanRequest,
    SubmissionDetail,
    SubmissionOut,
    SubmissionUpdate,
    UploadResponse,
    UploadResult,
)
from backend.models.grading_job import GradingJob
from backend.schemas.grading_job import GradingJobDetail, GradingJobOut
from backend.services.grading_service import GradingInProgressError, scan_similarity
from backend.services.job_service import cancel_job, enqueue_grading_job
from backend.utils.auth_utils import get_current_user
from backend.utils.file_utils import (
    FileTooLargeError,
    UnsupportedFileError,
    delete_file,
    extract_identity_from_parsed,
    guess_student_name,
    save_upload,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["submissions"])

_SUBMISSION_EXTS = {".ipynb", ".html", ".htm", ".py"}

# A class is a few hundred students. Anything past this is a malformed or
# hostile archive, not a submission bundle.
MAX_ZIP_MEMBERS = 1000


def _persist_one(
    db: Session, assignment: Assignment, stream: BinaryIO, filename: str,
) -> tuple[bool, UploadResult]:
    """Save one submission file and create its row. Returns (ok, result)."""
    try:
        path, size, file_type = save_upload(stream, filename, assignment.id)
    except (UnsupportedFileError, FileTooLargeError) as exc:
        return False, UploadResult(filename=filename, ok=False, error=str(exc))
    except OSError as exc:
        return False, UploadResult(
            filename=filename, ok=False, error=f"Could not save file: {exc}"
        )

    # Identity from the filename first (fast, no parse); fall back to reading
    # the student's name/id out of the file when the filename says nothing.
    student_name = guess_student_name(filename)
    student_id = None
    if not student_name:
        try:
            student_name, student_id = extract_identity_from_parsed(
                parse_submission(path)
            )
        except Exception:  # noqa: BLE001 - identity detection never fails an upload
            pass

    submission = Submission(
        assignment_id=assignment.id,
        student_name=student_name,
        student_id_external=student_id,
        original_filename=filename,
        file_path=str(path),
        file_type=file_type,
        file_size_bytes=size,
        status="pending",
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)
    return True, UploadResult(
        filename=filename, ok=True,
        submission_id=submission.id, student_name=student_name,
    )


def _zip_members(data: bytes) -> Iterator[tuple[str, bytes]]:
    """
    Yield (basename, bytes) for each gradeable file in a zip archive.

    A zip is untrusted input, so two limits apply *before* anything is
    decompressed:

      * `info.file_size` (the declared uncompressed size) is checked against
        the per-file limit. Without this a few KB on disk can expand to
        gigabytes in memory - `archive.read()` has no size ceiling of its
        own, and the streaming check in `save_upload` happens too late to
        prevent the expansion.
      * at most MAX_ZIP_MEMBERS files are taken, so an archive of a million
        one-byte entries cannot turn into a million database rows.

    Over-sized members are skipped rather than failing the whole upload: one
    bad file in a Canvas bundle must not reject the other 199.
    """
    max_bytes = settings.max_file_size_mb * 1024 * 1024
    taken = 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for info in archive.infolist():
            if taken >= MAX_ZIP_MEMBERS:
                logger.warning(
                    "Zip contains more than %d gradeable files; the rest were "
                    "ignored.", MAX_ZIP_MEMBERS,
                )
                break
            if info.is_dir() or "__MACOSX" in info.filename:
                continue
            base = info.filename.replace("\\", "/").split("/")[-1]
            if not base or base.startswith("."):
                continue
            if Path(base).suffix.lower() not in _SUBMISSION_EXTS:
                continue
            if info.file_size > max_bytes:
                logger.warning(
                    "Skipping %s from zip: declared uncompressed size %d bytes "
                    "exceeds the %d MB limit.",
                    base, info.file_size, settings.max_file_size_mb,
                )
                continue
            taken += 1
            yield base, archive.read(info)


def _persist_zip(
    db: Session, assignment: Assignment, stream: BinaryIO, filename: str,
) -> list[tuple[bool, UploadResult]]:
    """
    Extract a zip (e.g. a Canvas "Download Submissions" bundle) and save one
    submission per gradeable file inside it. Nested folders are flattened; junk
    like __MACOSX and dotfiles is skipped.
    """
    max_bytes = settings.max_file_size_mb * 1024 * 1024 * 5
    data = stream.read(max_bytes + 1)
    if len(data) > max_bytes:
        return [(False, UploadResult(
            filename=filename, ok=False,
            error=f"Zip exceeds the {settings.max_file_size_mb * 5} MB limit.",
        ))]
    try:
        members = list(_zip_members(data))
    except zipfile.BadZipFile:
        return [(False, UploadResult(
            filename=filename, ok=False,
            error=f"{filename} is not a valid zip file.",
        ))]

    if not members:
        return [(False, UploadResult(
            filename=filename, ok=False,
            error=f"{filename} contained no .ipynb, .html, or .py files.",
        ))]

    return [_persist_one(db, assignment, io.BytesIO(mbytes), mname)
            for mname, mbytes in members]


# ---------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------
@router.post(
    "/assignments/{assignment_id}/submissions",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_submissions(
    files: list[UploadFile] = File(..., description=".ipynb, .html or .py files"),
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> UploadResponse:
    """
    Upload one or many student files.

    A rejected file never aborts the batch: each result carries its own
    ok/error so the professor can see exactly which uploads need
    attention and re-send only those.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No files were uploaded"
        )

    results: list[UploadResult] = []
    uploaded = failed = 0

    for upload in files:
        filename = upload.filename or "unnamed"

        # A .zip (e.g. Canvas "Download Submissions") becomes one submission
        # per gradeable file inside it; anything else is one submission.
        if filename.lower().endswith(".zip"):
            outcomes = _persist_zip(db, assignment, upload.file, filename)
        else:
            outcomes = [_persist_one(db, assignment, upload.file, filename)]

        for ok, result in outcomes:
            uploaded += int(ok)
            failed += int(not ok)
            results.append(result)

    return UploadResponse(
        assignment_id=assignment.id,
        uploaded=uploaded, failed=failed, results=results,
    )


@router.get(
    "/assignments/{assignment_id}/submissions",
    response_model=list[SubmissionOut],
)
def list_submissions(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
    status_filter: str | None = None,
) -> list[SubmissionOut]:
    """Every submission for an assignment, optionally filtered by status."""
    query = db.query(Submission).filter(Submission.assignment_id == assignment.id)
    if status_filter:
        query = query.filter(Submission.status == status_filter)
    return [
        SubmissionOut.model_validate(s)
        for s in query.order_by(Submission.submitted_at).all()
    ]


@router.get("/submissions/{submission_id}", response_model=SubmissionDetail)
def get_submission(
    submission: Submission = Depends(get_owned_submission),
) -> SubmissionDetail:
    """One submission, including its cached parse result."""
    return SubmissionDetail.model_validate(submission)


@router.patch("/submissions/{submission_id}", response_model=SubmissionOut)
def update_submission(
    payload: SubmissionUpdate,
    submission: Submission = Depends(get_owned_submission),
    db: Session = Depends(get_db),
) -> SubmissionOut:
    """
    Correct the student identity.

    The filename heuristic gets names wrong often enough that this is a
    routine part of the workflow, not an edge case.
    """
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )
    for field, value in changes.items():
        setattr(submission, field, value)
    db.commit()
    db.refresh(submission)
    return SubmissionOut.model_validate(submission)


@router.delete("/submissions/{submission_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_submission(
    submission: Submission = Depends(get_owned_submission),
    db: Session = Depends(get_db),
) -> Response:
    """Delete a submission, its grade, and its uploaded file."""
    try:
        delete_file(submission.file_path)
    except (ValueError, OSError):
        # The row must go even if the file is already gone or unreachable.
        pass
    db.delete(submission)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------
# Grading
# ---------------------------------------------------------------------
@router.post(
    "/assignments/{assignment_id}/grade",
    response_model=GradingJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
def grade(
    payload: GradeRequest | None = None,
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradingJobOut:
    """
    Queue a grading run and return immediately.

    This used to grade inline, which meant a request held open for the
    length of the batch - over an hour for a large class. A proxy timeout,
    a browser refresh or a restart lost the run and the model spend with
    it. Now the work is a row in `grading_jobs`: a worker picks it up, the
    caller polls `GET /api/jobs/{id}`, and the run survives all three.

    202, not 200: the grading has been accepted, not performed. A second
    request while one is still queued or running gets 409.
    """
    payload = payload or GradeRequest()
    try:
        job = enqueue_grading_job(
            db, assignment, current_user,
            submission_ids=payload.submission_ids,
            regrade=payload.regrade,
            include_images=payload.include_images,
        )
    except GradingInProgressError as exc:
        # 409, not 500: the request was valid, the resource is busy.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return GradingJobOut.model_validate(job)


@router.get("/jobs/{job_id}", response_model=GradingJobDetail, tags=["jobs"])
def get_job(job: GradingJob = Depends(get_owned_job)) -> GradingJobDetail:
    """
    One job's status. This is the endpoint the UI polls, so it stays cheap:
    a single indexed row, no joins, no submission scan.
    """
    return GradingJobDetail.model_validate(job)


@router.get(
    "/assignments/{assignment_id}/jobs/latest",
    response_model=GradingJobDetail | None,
    tags=["jobs"],
)
def latest_job(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> GradingJobDetail | None:
    """
    The most recent job for an assignment, if any.

    This is what lets the UI recover after a refresh: the browser has
    forgotten the job id, but the assignment has not forgotten the job.
    """
    job = (
        db.query(GradingJob)
        .filter(GradingJob.assignment_id == assignment.id)
        .order_by(GradingJob.created_at.desc())
        .first()
    )
    return GradingJobDetail.model_validate(job) if job else None


@router.post("/jobs/{job_id}/cancel", response_model=GradingJobOut, tags=["jobs"])
def cancel(
    job: GradingJob = Depends(get_owned_job),
    db: Session = Depends(get_db),
) -> GradingJobOut:
    """
    Stop a run. A queued job stops at once; a running one stops after the
    submission currently being graded, so nothing is left half-written.
    Grades already written stay written.
    """
    return GradingJobOut.model_validate(cancel_job(db, job))


# ---------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------
def _flag_detail(db: Session, flag: SimilarityFlag) -> SimilarityFlagDetail:
    detail = SimilarityFlagDetail.model_validate(flag)
    names = {
        s.id: s.student_name
        for s in db.query(Submission).filter(
            Submission.id.in_([flag.submission_a_id, flag.submission_b_id])
        ).all()
    }
    detail.student_a_name = names.get(flag.submission_a_id)
    detail.student_b_name = names.get(flag.submission_b_id)
    return detail


@router.post(
    "/assignments/{assignment_id}/similarity",
    response_model=list[SimilarityFlagDetail],
    tags=["similarity"],
)
def run_similarity_scan(
    payload: SimilarityScanRequest | None = None,
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> list[SimilarityFlagDetail]:
    """
    Compare every pair of submissions and record flags.

    Flags a professor has already reviewed are never removed or
    duplicated by a rescan.
    """
    payload = payload or SimilarityScanRequest()
    flags = scan_similarity(
        db, assignment,
        threshold=payload.threshold,
        clear_existing=payload.clear_existing,
    )
    return [_flag_detail(db, f) for f in flags]


@router.get(
    "/assignments/{assignment_id}/similarity",
    response_model=list[SimilarityFlagDetail],
    tags=["similarity"],
)
def list_similarity_flags(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
    include_reviewed: bool = True,
) -> list[SimilarityFlagDetail]:
    """Existing similarity flags, highest score first."""
    query = db.query(SimilarityFlag).filter(
        SimilarityFlag.assignment_id == assignment.id
    )
    if not include_reviewed:
        query = query.filter(SimilarityFlag.reviewed.is_(False))
    flags = query.order_by(SimilarityFlag.similarity_score.desc()).all()
    return [_flag_detail(db, f) for f in flags]


@router.patch(
    "/similarity/{flag_id}",
    response_model=SimilarityFlagDetail,
    tags=["similarity"],
)
def review_similarity_flag(
    flag_id: str,
    payload: SimilarityReviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SimilarityFlagDetail:
    """Mark a flag reviewed and attach the professor's note."""
    from backend.models.course import Course

    flag = (
        db.query(SimilarityFlag)
        .join(Assignment, SimilarityFlag.assignment_id == Assignment.id)
        .join(Course, Assignment.course_id == Course.id)
        .filter(SimilarityFlag.id == flag_id, Course.user_id == current_user.id)
        .first()
    )
    if flag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Similarity flag not found"
        )

    flag.reviewed = payload.reviewed
    if payload.professor_note is not None:
        flag.professor_note = payload.professor_note
    db.commit()
    db.refresh(flag)
    return _flag_detail(db, flag)
