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

__all__ = [
    "User", "UserRole",
    "Course",
    "Assignment",
    "Submission",
    "GradeResult",
    "SimilarityFlag",
]
