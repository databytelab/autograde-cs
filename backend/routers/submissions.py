"""Submission upload, grading kick-off, and similarity scanning."""
from __future__ import annotations

from datetime import datetime

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

from backend.database import get_db
from backend.models.assignment import Assignment
from backend.models.similarity_flag import SimilarityFlag
from backend.models.submission import Submission
from backend.models.user import User
from backend.parsers import parse_submission
from backend.routers.deps import get_owned_assignment, get_owned_submission
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
from backend.services.grading_service import grade_assignment, scan_similarity
from backend.utils.auth_utils import get_current_user
from backend.utils.file_utils import (
    FileTooLargeError,
    UnsupportedFileError,
    delete_file,
    extract_identity_from_parsed,
    guess_student_name,
    save_upload,
)

router = APIRouter(prefix="/api", tags=["submissions"])


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
        try:
            path, size, file_type = save_upload(upload.file, filename, assignment.id)
        except (UnsupportedFileError, FileTooLargeError) as exc:
            failed += 1
            results.append(UploadResult(filename=filename, ok=False, error=str(exc)))
            continue
        except OSError as exc:
            failed += 1
            results.append(UploadResult(
                filename=filename, ok=False, error=f"Could not save file: {exc}"
            ))
            continue

        # Identity comes from the filename first (fast, no parse). When the
        # filename tells us nothing, read the student's name/id from inside
        # the file. Either source can leave it blank - the professor can
        # correct it in the UI.
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

        uploaded += 1
        results.append(UploadResult(
            filename=filename, ok=True,
            submission_id=submission.id, student_name=student_name,
        ))

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
@router.post("/assignments/{assignment_id}/grade", response_model=GradeResponse)
def grade(
    payload: GradeRequest | None = None,
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> GradeResponse:
    """
    Grade submissions.

    Runs synchronously - a batch of 30 notebooks takes a few minutes, and
    a professor watching a progress bar is a better experience than a job
    id they have to poll. Individual failures are reported per submission
    rather than failing the request.
    """
    payload = payload or GradeRequest()
    summary = grade_assignment(
        db, assignment,
        submission_ids=payload.submission_ids,
        regrade=payload.regrade,
        include_images=payload.include_images,
    )
    return GradeResponse(**summary)


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
