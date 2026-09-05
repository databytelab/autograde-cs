"""Assignment CRUD, rubric handling, and the instructor solution upload."""
from __future__ import annotations

from datetime import datetime

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.assignment import Assignment
from backend.models.course import Course
from backend.models.user import User
from backend.parsers import ParseError, parse_submission
from backend.routers.deps import get_owned_assignment, get_owned_course
from backend.schemas.assignment import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    RubricPreviewRequest,
)
from backend.services.rubric_service import (
    RubricError,
    build_default_rubric,
    build_rubric_from_solution,
    parse_rubric_text,
    validate_rubric,
)
from backend.utils.auth_utils import get_current_user, require_professor
from backend.utils.file_utils import (
    FileTooLargeError,
    UnsupportedFileError,
    delete_assignment_files,
    delete_file,
    save_upload,
)

router = APIRouter(prefix="/api/assignments", tags=["assignments"])


def _to_out(assignment: Assignment) -> AssignmentOut:
    out = AssignmentOut.model_validate(assignment)
    out.submission_count = assignment.submission_count
    out.graded_count = assignment.graded_count
    return out


@router.get("", response_model=list[AssignmentOut])
def list_assignments(
    course_id: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AssignmentOut]:
    """
    Assignments across every course the user owns.

    Pass `course_id` to narrow to one course.
    """
    query = (
        db.query(Assignment)
        .join(Course, Assignment.course_id == Course.id)
        .filter(Course.user_id == current_user.id)
    )
    if course_id:
        query = query.filter(Assignment.course_id == course_id)

    assignments = query.order_by(Assignment.created_at.desc()).all()
    return [_to_out(a) for a in assignments]


@router.post("", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: AssignmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AssignmentOut:
    """
    Create an assignment.

    The rubric comes from `rubric_json`, from `rubric_raw_text` (which
    Claude converts), or is generated as a default. It is always
    validated before it is stored, so an assignment in the database never
    holds a malformed rubric.
    """
    course = db.query(Course).filter(
        Course.id == payload.course_id, Course.user_id == current_user.id
    ).first()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )

    try:
        if payload.rubric_json:
            rubric = validate_rubric(payload.rubric_json)
        elif payload.rubric_raw_text:
            rubric = parse_rubric_text(
                payload.rubric_raw_text, payload.total_possible_points,
                provider=_provider_for(db, current_user),
            )
        else:
            rubric = build_default_rubric(payload.total_possible_points)
    except RubricError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        # A GradingError from the rubric-extraction call - almost always a
        # missing or rejected API key.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc

    assignment = Assignment(
        course_id=course.id,
        name=payload.name.strip(),
        description=payload.description,
        rubric_json=rubric,
        rubric_raw_text=payload.rubric_raw_text,
        # The rubric is the authority on the point total.
        total_possible_points=rubric["total_points"],
        due_date=payload.due_date,
        canvas_assignment_id=payload.canvas_assignment_id,
        status="pending",
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return _to_out(assignment)


@router.get("/{assignment_id}", response_model=AssignmentOut)
def get_assignment(
    assignment: Assignment = Depends(get_owned_assignment),
) -> AssignmentOut:
    return _to_out(assignment)


@router.patch("/{assignment_id}", response_model=AssignmentOut)
def update_assignment(
    payload: AssignmentUpdate,
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> AssignmentOut:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No fields to update"
        )

    if "rubric_json" in changes and changes["rubric_json"] is not None:
        try:
            rubric = validate_rubric(changes["rubric_json"])
        except RubricError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        changes["rubric_json"] = rubric
        # Keep the stored total in step with the rubric it came from.
        changes.setdefault("total_possible_points", rubric["total_points"])

    for field, value in changes.items():
        setattr(assignment, field, value)
    assignment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(assignment)
    return _to_out(assignment)


@router.delete("/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_assignment(
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
    _professor: User = Depends(require_professor),
) -> Response:
    """Delete an assignment, its submissions, its grades, and its files."""
    delete_assignment_files(assignment.id)
    db.delete(assignment)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------
# Rubrics
# ---------------------------------------------------------------------
def _provider_for(db: Session, user: User):
    """
    The AI this professor grades with, for the rubric calls too.

    Rubric generation used the server-wide provider. On an installation
    where the only credentials are the professor's own - which is every
    single-professor install - building a rubric failed with "OPENAI_API_KEY
    is not set ... see .env.example", at the first step of the first
    assignment. A provider that cannot be resolved falls back to the
    server-wide one rather than breaking the request.
    """
    from backend.services.credential_service import resolve_provider_for_user

    try:
        return resolve_provider_for_user(db, user)
    except Exception:  # noqa: BLE001 - fall back, never fail the request here
        return None


@router.post("/rubric/preview", tags=["rubrics"])
def preview_rubric(payload: RubricPreviewRequest,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)) -> dict:
    """
    Turn assignment prose into a rubric without saving anything.

    Lets a professor iterate on the wording until the extracted criteria
    look right, then create the assignment with the result.

    Uses this professor's own AI credentials when they have them, the same
    as grading does.
    """
    try:
        return parse_rubric_text(payload.text, payload.total_points,
                                 provider=_provider_for(db, current_user))
    except RubricError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc


@router.post("/rubric/from-solution", tags=["rubrics"])
def rubric_from_solution(
    file: UploadFile = File(...),
    total_points: float = Form(100.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Build a rubric from an uploaded instructor solution (.ipynb / .html / .py).

    The file is parsed and read by the model, which derives grading criteria
    that judge the underlying work rather than an exact match - student code
    and output legitimately vary. Nothing is saved: the professor reviews the
    result, then creates the assignment with it (and can attach the same file
    as the reference solution for grading).
    """
    try:
        path, _size, _ftype = save_upload(
            file.file, file.filename or "solution", "_rubric_preview"
        )
    except UnsupportedFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc

    try:
        parsed = parse_submission(path)
        rubric = build_rubric_from_solution(
            parsed, total_points=total_points,
            provider=_provider_for(db, current_user))
    except ParseError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Could not read the solution file: {exc}",
        ) from exc
    except RubricError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except RuntimeError as exc:
        # A GradingError from the extraction call - almost always a missing
        # or rejected API key.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from exc
    finally:
        delete_file(path)

    return rubric


@router.get("/{assignment_id}/rubric", tags=["rubrics"])
def get_rubric(assignment: Assignment = Depends(get_owned_assignment)) -> dict:
    """The assignment's rubric, or the default if none was set."""
    if assignment.rubric_json:
        try:
            return validate_rubric(assignment.rubric_json)
        except RubricError:
            pass
    return build_default_rubric(float(assignment.total_possible_points or 100.0))


# ---------------------------------------------------------------------
# Instructor solution
# ---------------------------------------------------------------------
@router.post("/{assignment_id}/solution", response_model=AssignmentOut)
def upload_solution(
    file: UploadFile = File(...),
    assignment: Assignment = Depends(get_owned_assignment),
    db: Session = Depends(get_db),
) -> AssignmentOut:
    """
    Attach a solved reference notebook.

    The grader passes it to Claude as the expected result, which makes
    correctness judgements markedly more reliable than the rubric text
    alone.
    """
    try:
        path, _size, _ftype = save_upload(
            file.file, file.filename or "solution.ipynb",
            f"{assignment.id}/_solution",
        )
    except UnsupportedFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=str(exc)
        ) from exc
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)
        ) from exc

    assignment.expected_submission_path = str(path)
    assignment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(assignment)
    return _to_out(assignment)
