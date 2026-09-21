"""Grade export and Canvas push-back."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.assignment import Assignment
from backend.models.submission import Submission
from backend.models.user import User
from backend.routers.deps import get_owned_assignment
from backend.services import canvas_service
from backend.services.credential_service import canvas_credentials_for
from backend.services.export_service import FORMATS, export
from backend.utils.auth_utils import get_current_user, require_professor

router = APIRouter(prefix="/api", tags=["export"])


@router.get("/assignments/{assignment_id}/export")
def export_grades(
    fmt: str = Query(
        "csv", alias="format",
        description=f"One of: {', '.join(sorted(FORMATS))}",
    ),
    only_finalized: bool = Query(
        False, description="Export only grades the professor has approved."
    ),
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> Response:
    """
    Download grades as CSV, Canvas CSV, XLSX, or a PDF feedback packet.

    Returns the file inline as an attachment - nothing is written to
    the server's filesystem.
    """
    try:
        payload, media_type, filename = export(
            db, assignment, fmt,
            only_finalized=only_finalized,
            course_name=assignment.course.name if assignment.course else "",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        ) from exc

    return Response(
        content=payload,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------
@router.get("/canvas/status", tags=["canvas"])
def canvas_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Whether *this instructor* can talk to Canvas.

    Their own connection wins; a server-wide one in .env is the fallback,
    which is what a single-instructor install uses.
    """
    base_url, token = canvas_credentials_for(db, current_user)
    if base_url and token:
        return {"configured": True, "base_url": base_url, "source": "personal"}
    if canvas_service.settings.canvas_base_url and \
            canvas_service.settings.canvas_api_token:
        return {"configured": True,
                "base_url": canvas_service.settings.canvas_base_url,
                "source": "server"}
    return {"configured": False, "base_url": None, "source": None}


@router.get("/canvas/courses", tags=["canvas"])
def canvas_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Canvas courses the configured token can teach."""
    try:
        with canvas_service.use_credentials(*canvas_credentials_for(db, current_user)):
            return canvas_service.list_courses()
    except canvas_service.CanvasNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    except canvas_service.CanvasError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.get("/canvas/courses/{canvas_course_id}/assignments", tags=["canvas"])
def canvas_assignments(
    canvas_course_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Assignments in a Canvas course, for linking to a local assignment."""
    try:
        with canvas_service.use_credentials(*canvas_credentials_for(db, current_user)):
            return canvas_service.list_assignments(canvas_course_id)
    except canvas_service.CanvasNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    except canvas_service.CanvasError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc


@router.post("/assignments/{assignment_id}/canvas/sync-roster", tags=["canvas"])
def sync_roster(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Match this assignment's submissions against the Canvas roster.

    Fills in `student_email` and `student_id_external` where a confident
    match exists. Unmatched submissions are listed by name so the
    professor can fix them by hand - we never guess.
    """
    course = assignment.course
    if not course or not course.canvas_course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This course has no canvas_course_id set.",
        )

    try:
        with canvas_service.use_credentials(*canvas_credentials_for(db, current_user)):
            roster = canvas_service.get_roster(course.canvas_course_id)
    except canvas_service.CanvasNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    except canvas_service.CanvasError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    submissions = db.query(Submission).filter(
        Submission.assignment_id == assignment.id
    ).all()

    matched, unmatched = 0, []
    for submission in submissions:
        entry = canvas_service.match_student(
            roster, name=submission.student_name, email=submission.student_email
        )
        if entry is None:
            unmatched.append({
                "submission_id": submission.id,
                "student_name": submission.student_name,
                "filename": submission.original_filename,
            })
            continue
        submission.student_id_external = entry["canvas_user_id"]
        submission.student_email = entry["email"] or submission.student_email
        submission.student_name = entry["name"] or submission.student_name
        matched += 1

    db.commit()
    return {
        "roster_size": len(roster),
        "matched": matched,
        "unmatched": unmatched,
    }


def _canvas_comment(grade) -> str:
    """
    The feedback comment posted to a student in Canvas: the overall summary
    only. The per-criterion breakdown stays inside AutoGrade (Review results,
    and the PDF/Excel exports) rather than going into Canvas, which a
    student reads as one paragraph, not a rubric table.
    """
    return (grade.summary_feedback or "").strip()


@router.post("/assignments/{assignment_id}/canvas/push-grades", tags=["canvas"])
def push_grades(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_professor),
    only_finalized: bool = Query(
        True,
        description="Push only approved grades. Turn this off at your own risk.",
    ),
) -> dict:
    """
    Write grades into the Canvas gradebook.

    Professors only, and finalized grades only by default - pushing an
    unreviewed AI grade into a student's record is not something this
    tool should make easy.
    """
    course = assignment.course
    if not course or not course.canvas_course_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This course has no canvas_course_id set.",
        )
    if not assignment.canvas_assignment_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This assignment has no canvas_assignment_id set.",
        )

    submissions = db.query(Submission).filter(
        Submission.assignment_id == assignment.id
    ).all()

    payload, skipped = [], []
    for submission in submissions:
        grade = submission.grade_result
        if grade is None:
            skipped.append({"student_name": submission.student_name,
                            "reason": "not graded"})
            continue
        if only_finalized and not grade.finalized:
            skipped.append({"student_name": submission.student_name,
                            "reason": "not finalized"})
            continue
        if not submission.student_id_external:
            skipped.append({"student_name": submission.student_name,
                            "reason": "no Canvas user id - run sync-roster first"})
            continue

        # Push the PERCENTAGE (e.g. "96%"), not the raw rubric score. Canvas
        # scales a percentage to whatever the assignment is worth there, so a
        # 100-point rubric maps correctly onto a 3-point Canvas assignment.
        payload.append({
            "canvas_user_id": submission.student_id_external,
            "score": f"{round(float(grade.percentage or 0), 2)}%",
            "comment": _canvas_comment(grade),
        })

    if not payload:
        return {"submitted": 0, "skipped": skipped,
                "message": "Nothing to push. See `skipped` for why."}

    try:
        with canvas_service.use_credentials(*canvas_credentials_for(db, current_user)):
            outcome = canvas_service.push_grades_bulk(
                course.canvas_course_id, assignment.canvas_assignment_id, payload
            )
    except canvas_service.CanvasNotConfigured as exc:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED, detail=str(exc)
        ) from exc
    except canvas_service.CanvasError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    return {**outcome, "skipped": skipped}
