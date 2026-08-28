"""Course CRUD. A course belongs to exactly one professor."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.course import Course
from backend.models.user import User
from backend.routers.deps import get_owned_course
from backend.schemas.course import CourseCreate, CourseOut, CourseUpdate
from backend.utils.auth_utils import get_current_user, require_professor

router = APIRouter(prefix="/api/courses", tags=["courses"])


def _to_out(course: Course) -> CourseOut:
    out = CourseOut.model_validate(course)
    out.assignment_count = course.assignment_count
    return out


@router.get("", response_model=list[CourseOut])
def list_courses(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CourseOut]:
    """Every course owned by the current user, newest first."""
    courses = (
        db.query(Course)
        .filter(Course.user_id == current_user.id)
        .order_by(Course.created_at.desc())
        .all()
    )
    return [_to_out(c) for c in courses]


@router.post("", response_model=CourseOut, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CourseOut:
    course = Course(
        user_id=current_user.id,
        name=payload.name.strip(),
        term=payload.term,
        canvas_course_id=payload.canvas_course_id,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return _to_out(course)


@router.get("/{course_id}", response_model=CourseOut)
def get_course(course: Course = Depends(get_owned_course)) -> CourseOut:
    return _to_out(course)


@router.patch("/{course_id}", response_model=CourseOut)
def update_course(
    payload: CourseUpdate,
    course: Course = Depends(get_owned_course),
    db: Session = Depends(get_db),
) -> CourseOut:
    """Partial update - only the fields present in the body change."""
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No fields to update",
        )

    for field, value in changes.items():
        setattr(course, field, value)
    course.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(course)
    return _to_out(course)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(
    course: Course = Depends(get_owned_course),
    db: Session = Depends(get_db),
    _professor: User = Depends(require_professor),
) -> Response:
    """
    Delete a course and everything under it.

    Assignments, submissions and grades cascade at the database level.
    Uploaded files are removed per assignment first, because once the
    rows are gone we no longer know which folders belonged to it.
    """
    from backend.utils.file_utils import delete_assignment_files

    for assignment in course.assignments:
        delete_assignment_files(assignment.id)

    db.delete(course)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
