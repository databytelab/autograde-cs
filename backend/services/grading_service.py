"""
Grading orchestration.

The routers stay thin: they authenticate, then call into here. This
module owns the workflow - parse, grade, persist, update statuses - and
is the only place that knows the order those things happen in.

Failure policy: one bad submission never stops a batch. A submission that
cannot be parsed or graded is marked `error` with the reason stored on
the row, and the run continues.
"""
from __future__ import annotations

import logging
import statistics
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session, joinedload

from backend.ai.grader import GradingError, grade_submission
from backend.models.assignment import Assignment, AssignmentStatus
from backend.models.grade_result import GradeResult
from backend.models.similarity_flag import SimilarityFlag
from backend.models.submission import Submission, SubmissionStatus
from backend.parsers import ParseError, parse_submission
from backend.services.rubric_service import (
    RubricError,
    build_default_rubric,
    letter_grade,
    validate_rubric,
)
from backend.utils.similarity import build_fingerprint, find_similar_pairs

logger = logging.getLogger(__name__)

# How long an assignment may sit in `grading` before another run assumes the
# previous one died and takes over. Long enough for a real batch (a few
# hundred submissions at ~20s each), short enough to self-heal after a crash
# without an administrator having to touch the database.
GRADING_LOCK_TIMEOUT = timedelta(hours=3)


class GradingInProgressError(RuntimeError):
    """Raised when an assignment is already being graded."""


# ---------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------
def parse_and_cache(db: Session, submission: Submission) -> dict[str, Any]:
    """
    Parse a submission, caching the result on the row.

    Re-parsing is skipped when `parsed_content` is already populated, so
    a regrade does not redo the work. Raises ParseError on failure, after
    marking the submission.
    """
    if submission.parsed_content:
        return submission.parsed_content

    submission.status = SubmissionStatus.PARSING
    db.commit()

    try:
        parsed = parse_submission(submission.file_path)
    except ParseError as exc:
        submission.status = SubmissionStatus.ERROR
        submission.error_message = str(exc)
        db.commit()
        raise

    submission.parsed_content = parsed
    submission.error_message = None
    submission.status = SubmissionStatus.PENDING
    db.commit()
    return parsed


# ---------------------------------------------------------------------
# Rubric resolution
# ---------------------------------------------------------------------
def resolve_rubric(assignment: Assignment) -> dict[str, Any]:
    """
    Return the validated rubric to grade this assignment against.

    Falls back to a generated default so that an assignment created
    without a rubric is still gradeable rather than a dead end.
    """
    if assignment.rubric_json:
        try:
            return validate_rubric(assignment.rubric_json)
        except RubricError as exc:
            logger.warning(
                "Assignment %s has an invalid stored rubric (%s); "
                "falling back to the default rubric.", assignment.id, exc
            )
    return build_default_rubric(float(assignment.total_possible_points or 100.0))


# ---------------------------------------------------------------------
# Grading one submission
# ---------------------------------------------------------------------
def grade_one(
    db: Session,
    submission: Submission,
    assignment: Assignment,
    rubric: dict[str, Any],
    *,
    include_images: bool = True,
) -> GradeResult:
    """
    Parse (if needed), grade, and persist one submission.

    Raises ParseError or GradingError; the submission row is marked
    `error` before the exception propagates so the caller only has to
    record it.
    """
    parsed = parse_and_cache(db, submission)

    submission.status = SubmissionStatus.GRADING
    db.commit()

    expected = None
    if assignment.expected_submission_path:
        try:
            expected = parse_submission(assignment.expected_submission_path)
        except ParseError as exc:
            # A broken reference solution degrades grading; it must not
            # block it.
            logger.warning(
                "Could not parse the reference solution for assignment %s: %s",
                assignment.id, exc,
            )

    try:
        result = grade_submission(
            parsed=parsed,
            rubric=rubric,
            assignment_name=assignment.name,
            assignment_description=assignment.description,
            expected_solution=expected,
            include_images=include_images,
        )
    except GradingError as exc:
        submission.status = SubmissionStatus.ERROR
        submission.error_message = str(exc)
        db.commit()
        raise

    grade = submission.grade_result or GradeResult(submission_id=submission.id)
    grade.total_score = result["total_score"]
    grade.total_possible = result["total_possible"]
    grade.percentage = result["percentage"]
    grade.letter_grade = result["letter_grade"]
    grade.criteria_results = result["criteria_results"]
    grade.flags = result["flags"]
    grade.ai_raw_output = result["ai_raw_output"]
    grade.summary_feedback = result["summary_feedback"]
    # A regrade invalidates a previous approval *and* the overrides that went
    # with it. The overrides were judgements about the previous AI scores and
    # are keyed by criterion id, so keeping them would silently reapply an old
    # adjustment to a fresh grade - and, because `total_score` is set from the
    # new AI result while `effective_score` re-adds the overrides, the export
    # (effective_score) and the Canvas push (percentage) would disagree.
    grade.professor_overrides = None
    grade.finalized = False
    grade.finalized_at = None
    grade.updated_at = datetime.utcnow()

    if grade not in db:
        db.add(grade)

    submission.status = (
        SubmissionStatus.FLAGGED if result["flags"] else SubmissionStatus.GRADED
    )
    submission.graded_at = datetime.utcnow()
    submission.error_message = None
    db.commit()
    db.refresh(grade)
    return grade


# ---------------------------------------------------------------------
# Grading a batch
# ---------------------------------------------------------------------
def grade_assignment(
    db: Session,
    assignment: Assignment,
    *,
    submission_ids: list[str] | None = None,
    regrade: bool = False,
    include_images: bool = True,
) -> dict[str, Any]:
    """
    Grade every eligible submission in an assignment.

    Returns a summary dict matching schemas.submission.GradeResponse.
    """
    # Refuse to run two batches over the same assignment at once. Without
    # this, a double-click or a second browser tab grades every submission
    # twice: double the model spend, and both runs race to create the same
    # GradeResult row (submission_id is unique), so one of them fails and
    # marks perfectly good submissions as errored. The lock self-heals - a
    # run that died leaves the status behind, so an old timestamp is treated
    # as abandoned rather than blocking the assignment forever.
    if assignment.status == AssignmentStatus.GRADING:
        started = assignment.updated_at or datetime.utcnow()
        if datetime.utcnow() - started < GRADING_LOCK_TIMEOUT:
            raise GradingInProgressError(
                "This assignment is already being graded. Wait for that run to "
                "finish before starting another."
            )
        logger.warning(
            "Assignment %s has been in 'grading' since %s; assuming the "
            "previous run died and taking over.", assignment.id, started,
        )

    rubric = resolve_rubric(assignment)

    # The loop below reads `grade_result` on every row to decide whether to
    # skip it, so it is eager-loaded rather than lazily fetched per student.
    query = (
        db.query(Submission)
        .options(joinedload(Submission.grade_result))
        .filter(Submission.assignment_id == assignment.id)
    )
    if submission_ids:
        query = query.filter(Submission.id.in_(submission_ids))
    submissions = query.order_by(Submission.submitted_at).all()

    assignment.status = AssignmentStatus.GRADING
    db.commit()

    results: list[dict[str, Any]] = []
    graded = failed = skipped = 0

    for submission in submissions:
        if submission.grade_result is not None and not regrade:
            skipped += 1
            results.append({
                "submission_id": submission.id,
                "student_name": submission.student_name,
                "ok": True,
                "total_score": float(submission.grade_result.total_score or 0),
                "percentage": float(submission.grade_result.percentage or 0),
                "letter_grade": submission.grade_result.letter_grade,
                "flags": submission.grade_result.flags or [],
                "error": None,
            })
            continue

        try:
            grade = grade_one(
                db, submission, assignment, rubric, include_images=include_images
            )
        except (ParseError, GradingError) as exc:
            failed += 1
            logger.warning("Grading failed for submission %s: %s", submission.id, exc)
            results.append({
                "submission_id": submission.id,
                "student_name": submission.student_name,
                "ok": False,
                "error": str(exc),
                "flags": [],
            })
            continue
        except Exception as exc:  # noqa: BLE001 - one bad row must not kill the batch
            failed += 1
            logger.exception("Unexpected error grading submission %s", submission.id)
            db.rollback()
            submission.status = SubmissionStatus.ERROR
            submission.error_message = f"Unexpected error: {exc}"
            db.commit()
            results.append({
                "submission_id": submission.id,
                "student_name": submission.student_name,
                "ok": False,
                "error": f"Unexpected error: {exc}",
                "flags": [],
            })
            continue

        graded += 1
        results.append({
            "submission_id": submission.id,
            "student_name": submission.student_name,
            "ok": True,
            "total_score": float(grade.total_score or 0),
            "percentage": float(grade.percentage or 0),
            "letter_grade": grade.letter_grade,
            "flags": grade.flags or [],
            "error": None,
        })

    remaining = db.query(Submission).filter(
        Submission.assignment_id == assignment.id,
        Submission.status.in_([SubmissionStatus.PENDING, SubmissionStatus.GRADING]),
    ).count()
    assignment.status = (
        AssignmentStatus.COMPLETE if remaining == 0 else AssignmentStatus.PENDING
    )
    db.commit()

    return {
        "assignment_id": assignment.id,
        "graded": graded,
        "failed": failed,
        "skipped": skipped,
        "results": results,
    }


# ---------------------------------------------------------------------
# Professor overrides
# ---------------------------------------------------------------------
def apply_overrides(
    db: Session,
    grade: GradeResult,
    overrides: dict[str, dict[str, Any]],
    summary_feedback: str | None = None,
) -> GradeResult:
    """
    Record professor score adjustments and recompute the totals.

    Overrides sit alongside the AI scores rather than replacing them, so
    `ai_raw_output` and `criteria_results` stay exactly as the model
    produced them. Unknown criterion ids are rejected.
    """
    known = {c["criterion_id"]: c for c in (grade.criteria_results or [])}
    unknown = set(overrides) - set(known)
    if unknown:
        raise ValueError(
            f"Unknown criterion id(s): {', '.join(sorted(unknown))}. "
            f"Valid ids: {', '.join(sorted(known))}"
        )

    for cid, override in overrides.items():
        new_score = float(override["new_score"])
        max_score = float(known[cid]["max_score"])
        if new_score > max_score:
            raise ValueError(
                f"Criterion '{known[cid]['name']}' caps at {max_score} points; "
                f"{new_score} was given."
            )
        # The API schema also bounds this, but apply_overrides is reachable
        # from scripts and future callers, so the invariant lives with the
        # logic that depends on it rather than only at the edge.
        if new_score < 0:
            raise ValueError(
                f"Criterion '{known[cid]['name']}' cannot be negative; "
                f"{new_score} was given."
            )

    merged = dict(grade.professor_overrides or {})
    merged.update({
        cid: {"new_score": float(o["new_score"]), "note": str(o.get("note") or "")}
        for cid, o in overrides.items()
    })
    grade.professor_overrides = merged

    total = grade.effective_score
    total_possible = float(grade.total_possible or 0)
    grade.total_score = round(total, 2)
    grade.percentage = round(total / total_possible * 100, 2) if total_possible else 0.0
    grade.letter_grade = letter_grade(grade.percentage)

    if summary_feedback is not None:
        grade.summary_feedback = summary_feedback

    grade.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(grade)
    return grade


def finalize_grade(db: Session, grade: GradeResult, finalized: bool = True) -> GradeResult:
    """Approve (or un-approve) a grade. Only a professor may call this."""
    grade.finalized = finalized
    grade.finalized_at = datetime.utcnow() if finalized else None
    grade.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(grade)
    return grade


# ---------------------------------------------------------------------
# Similarity scanning
# ---------------------------------------------------------------------
def scan_similarity(
    db: Session,
    assignment: Assignment,
    *,
    threshold: float = 0.5,
    clear_existing: bool = True,
) -> list[SimilarityFlag]:
    """
    Compare every pair of submissions in an assignment and record flags.

    Reviewed flags are preserved even when `clear_existing` is set - a
    professor's judgement is not thrown away by a rescan.
    """
    submissions = db.query(Submission).filter(
        Submission.assignment_id == assignment.id
    ).all()

    if clear_existing:
        db.query(SimilarityFlag).filter(
            SimilarityFlag.assignment_id == assignment.id,
            SimilarityFlag.reviewed.is_(False),
        ).delete(synchronize_session=False)
        db.commit()

    fingerprints = []
    for submission in submissions:
        try:
            parsed = parse_and_cache(db, submission)
        except ParseError:
            continue  # unparseable submissions simply do not participate
        fingerprints.append(build_fingerprint(submission.id, parsed))

    already_reviewed = {
        frozenset((f.submission_a_id, f.submission_b_id))
        for f in db.query(SimilarityFlag).filter(
            SimilarityFlag.assignment_id == assignment.id
        ).all()
    }

    created: list[SimilarityFlag] = []
    for pair in find_similar_pairs(fingerprints, threshold=threshold):
        key = frozenset((pair["submission_a_id"], pair["submission_b_id"]))
        if key in already_reviewed:
            continue
        flag = SimilarityFlag(
            assignment_id=assignment.id,
            submission_a_id=pair["submission_a_id"],
            submission_b_id=pair["submission_b_id"],
            similarity_score=pair["similarity_score"],
            severity=pair["severity"],
            method=pair["method"],
        )
        db.add(flag)
        created.append(flag)

    db.commit()
    for flag in created:
        db.refresh(flag)
    return created


# ---------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------
def assignment_stats(db: Session, assignment: Assignment) -> dict[str, Any]:
    """
    Dashboard numbers for one assignment.

    The grade is eager-loaded: this walks every submission reading
    `grade_result`, which lazily issued one SELECT per submission (203
    statements for a 200-student assignment). The dashboard calls this once
    per course, so the cost multiplied.
    """
    submissions = (
        db.query(Submission)
        .options(joinedload(Submission.grade_result))
        .filter(Submission.assignment_id == assignment.id)
        .all()
    )

    percentages: list[float] = []
    finalized = 0
    for submission in submissions:
        grade = submission.grade_result
        if grade and grade.percentage is not None:
            percentages.append(float(grade.percentage))
            if grade.finalized:
                finalized += 1

    distribution: dict[str, int] = {}
    for pct in percentages:
        letter = letter_grade(pct)
        distribution[letter] = distribution.get(letter, 0) + 1

    flagged = db.query(SimilarityFlag).filter(
        SimilarityFlag.assignment_id == assignment.id
    ).count()

    return {
        "assignment_id": assignment.id,
        "assignment_name": assignment.name,
        "total_submissions": len(submissions),
        "graded": sum(1 for s in submissions if s.grade_result is not None),
        "pending": sum(1 for s in submissions if s.status == SubmissionStatus.PENDING),
        "errored": sum(1 for s in submissions if s.status == SubmissionStatus.ERROR),
        "finalized": finalized,
        "flagged": flagged,
        "mean_percentage": round(statistics.mean(percentages), 2) if percentages else None,
        "median_percentage": round(statistics.median(percentages), 2) if percentages else None,
        "min_percentage": round(min(percentages), 2) if percentages else None,
        "max_percentage": round(max(percentages), 2) if percentages else None,
        "grade_distribution": dict(sorted(distribution.items())),
    }
