"""
Shared ownership lookups for the routers.

Every resource in this app hangs off a course, and every course has an
owner. These helpers do the "does this user own this thing" check once,
so no route has to remember to write it.

They deliberately return 404 rather than 403 for a resource owned by
someone else: telling a stranger that assignment X exists but is not
theirs leaks the existence of other professors' courses.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.assignment import Assignment
from backend.models.course import Course
from backend.models.grade_result import GradeResult
from backend.models.submission import Submission
from backend.models.user import User
from backend.utils.auth_utils import get_current_user


def get_owned_course(
    course_id: str = Path(..., description="Course id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Course:
    course = db.query(Course).filter(
        Course.id == course_id, Course.user_id == current_user.id
    ).first()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Course not found"
        )
    return course


def get_owned_assignment(
    assignment_id: str = Path(..., description="Assignment id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Assignment:
    assignment = (
        db.query(Assignment)
        .join(Course, Assignment.course_id == Course.id)
        .filter(Assignment.id == assignment_id, Course.user_id == current_user.id)
        .first()
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    return assignment


def get_owned_submission(
    submission_id: str = Path(..., description="Submission id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Submission:
    submission = (
        db.query(Submission)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .join(Course, Assignment.course_id == Course.id)
        .filter(Submission.id == submission_id, Course.user_id == current_user.id)
        .first()
    )
    if submission is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    return submission


def get_owned_job(
    job_id: str = Path(..., description="Grading job id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> "GradingJob":
    """
    A grading job the caller owns.

    Ownership is checked through the course, not through `grading_jobs.user_id`
    alone: a TA may start a run on a course they work on, and the professor
    who owns the course must still be able to see and cancel it. The
    `user_id` column records who started it; this decides who may touch it.
    """
    from backend.models.grading_job import GradingJob

    job = (
        db.query(GradingJob)
        .join(Assignment, GradingJob.assignment_id == Assignment.id)
        .join(Course, Assignment.course_id == Course.id)
        .filter(GradingJob.id == job_id, Course.user_id == current_user.id)
        .first()
    )
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grading job not found"
        )
    return job


def get_owned_grade(
    grade_id: str = Path(..., description="Grade result id"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GradeResult:
    grade = (
        db.query(GradeResult)
        .join(Submission, GradeResult.submission_id == Submission.id)
        .join(Assignment, Submission.assignment_id == Assignment.id)
        .join(Course, Assignment.course_id == Course.id)
        .filter(GradeResult.id == grade_id, Course.user_id == current_user.id)
        .first()
    )
    if grade is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Grade result not found"
        )
    return grade
