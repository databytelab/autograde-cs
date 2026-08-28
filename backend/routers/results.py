"""Reading grades, applying professor overrides, and finalizing."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.assignment import Assignment
from backend.models.grade_result import GradeResult
from backend.models.submission import Submission
from backend.models.user import User
from backend.routers.deps import (
    get_owned_assignment,
    get_owned_grade,
    get_owned_submission,
)
from backend.schemas.grade_result import (
    AssignmentStats,
    FinalizeRequest,
    GradeResultDetail,
    GradeResultOut,
    OverrideRequest,
)
from backend.services.grading_service import (
    apply_overrides,
    assignment_stats,
    finalize_grade,
)
from backend.utils.auth_utils import require_professor

router = APIRouter(prefix="/api", tags=["results"])


def _to_out(grade: GradeResult, submission: Submission | None = None) -> GradeResultDetail:
    detail = GradeResultDetail.model_validate(grade)
    detail.effective_score = grade.effective_score
    if submission is not None:
        detail.student_name = submission.student_name
        detail.original_filename = submission.original_filename
    return detail


@router.get(
    "/assignments/{assignment_id}/results",
    response_model=list[GradeResultDetail],
)
def list_results(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
    finalized_only: bool = False,
    flagged_only: bool = False,
) -> list[GradeResultDetail]:
    """
    Every grade for an assignment.

    `flagged_only` narrows to results the grader raised an integrity or
    quality flag on - the queue a professor works through first.
    """
    query = (
        db.query(GradeResult, Submission)
        .join(Submission, GradeResult.submission_id == Submission.id)
        .filter(Submission.assignment_id == assignment.id)
    )
    if finalized_only:
        query = query.filter(GradeResult.finalized.is_(True))

    rows = query.order_by(Submission.student_name).all()

    results = []
    for grade, submission in rows:
        if flagged_only and not (grade.flags or []):
            continue
        results.append(_to_out(grade, submission))
    return results


@router.get(
    "/submissions/{submission_id}/result",
    response_model=GradeResultDetail,
)
def get_result_for_submission(
    submission: Submission = Depends(get_owned_submission),
) -> GradeResultDetail:
    """The grade for one submission, including the raw model output."""
    if submission.grade_result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This submission has not been graded yet",
        )
    return _to_out(submission.grade_result, submission)


@router.patch("/results/{grade_id}/override", response_model=GradeResultOut)
def override_scores(
    payload: OverrideRequest,
    grade: GradeResult = Depends(get_owned_grade),
    db: Session = Depends(get_db),
) -> GradeResultOut:
    """
    Adjust one or more criterion scores.

    Overrides are stored next to the AI scores, never over them, so the
    original judgement remains auditable. Totals are recomputed here.
    """
    if grade.finalized:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This grade is finalized. Un-finalize it before editing scores.",
        )

    try:
        updated = apply_overrides(
            db, grade,
            {cid: o.model_dump() for cid, o in payload.overrides.items()},
            summary_feedback=payload.summary_feedback,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    out = GradeResultOut.model_validate(updated)
    out.effective_score = updated.effective_score
    return out


@router.post("/results/{grade_id}/finalize", response_model=GradeResultOut)
def finalize(
    payload: FinalizeRequest,
    grade: GradeResult = Depends(get_owned_grade),
    db: Session = Depends(get_db),
    _professor: User = Depends(require_professor),
) -> GradeResultOut:
    """
    Approve a grade. Professors only - a TA can grade but not approve.

    Finalizing is what makes a grade eligible for export and Canvas
    push-back.
    """
    updated = finalize_grade(db, grade, payload.finalized)
    out = GradeResultOut.model_validate(updated)
    out.effective_score = updated.effective_score
    return out


@router.get("/assignments/{assignment_id}/stats", response_model=AssignmentStats)
def get_stats(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> AssignmentStats:
    """Counts and score distribution for the dashboard."""
    return AssignmentStats(**assignment_stats(db, assignment))
