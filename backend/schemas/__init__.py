"""
Pydantic request/response models.

Import from here so route modules get everything with one import and the
names stay stable if a schema moves file.
"""
from backend.schemas.assignment import (
    AssignmentCreate,
    AssignmentOut,
    AssignmentUpdate,
    Rubric,
    RubricCriterion,
    RubricLevel,
    RubricPreviewRequest,
)
from backend.schemas.course import CourseCreate, CourseOut, CourseUpdate
from backend.schemas.grade_result import (
    AssignmentStats,
    CriterionOverride,
    CriterionResult,
    FinalizeRequest,
    GradeResultDetail,
    GradeResultOut,
    OverrideRequest,
)
from backend.schemas.submission import (
    GradeJobResult,
    GradeRequest,
    GradeResponse,
    SimilarityFlagDetail,
    SimilarityFlagOut,
    SimilarityReviewRequest,
    SimilarityScanRequest,
    SubmissionDetail,
    SubmissionOut,
    SubmissionUpdate,
    UploadResponse,
    UploadResult,
)
from backend.schemas.user import Token, UserCreate, UserLogin, UserOut

__all__ = [
    # user
    "UserCreate", "UserLogin", "UserOut", "Token",
    # course
    "CourseCreate", "CourseUpdate", "CourseOut",
    # assignment
    "AssignmentCreate", "AssignmentUpdate", "AssignmentOut",
    "Rubric", "RubricCriterion", "RubricLevel", "RubricPreviewRequest",
    # submission
    "SubmissionOut", "SubmissionDetail", "SubmissionUpdate",
    "UploadResult", "UploadResponse",
    "GradeRequest", "GradeJobResult", "GradeResponse",
    "SimilarityFlagOut", "SimilarityFlagDetail",
    "SimilarityScanRequest", "SimilarityReviewRequest",
    # grade result
    "CriterionResult", "GradeResultOut", "GradeResultDetail",
    "CriterionOverride", "OverrideRequest", "FinalizeRequest",
    "AssignmentStats",
]
