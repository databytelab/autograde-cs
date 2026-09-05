"""
Import all models here so:
1. Alembic can discover them for migrations
2. Any file that imports models gets them all with one import
"""
from backend.models.user            import User, UserRole
from backend.models.course          import Course
from backend.models.assignment      import Assignment
from backend.models.submission      import Submission
from backend.models.grade_result    import GradeResult
from backend.models.similarity_flag import SimilarityFlag
from backend.models.grading_job     import (
    ACTIVE_STATUSES, TERMINAL_STATUSES, GradingJob, JobStatus,
)
from backend.models.login_attempt   import LoginAttempt
from backend.models.provider_credential import (
    SUPPORTED_PROVIDERS, ProviderCredential,
)

__all__ = [
    "User", "UserRole",
    "Course",
    "Assignment",
    "Submission",
    "GradeResult",
    "SimilarityFlag",
    "GradingJob", "JobStatus", "ACTIVE_STATUSES", "TERMINAL_STATUSES",
    "LoginAttempt",
    "ProviderCredential", "SUPPORTED_PROVIDERS",
]
