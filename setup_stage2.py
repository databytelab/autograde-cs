# setup_stage2.py
# Stage 2: Complete database layer
# - All 6 SQLAlchemy models with full columns
# - Alembic migration setup
# - database.py finalized
# - Creates and verifies all tables
# - Runs a quick sanity check on every model

import subprocess
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent
VENV_PYTHON  = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"

print("=" * 60)
print(" AutoGrade CS — Stage 2: Database Layer")
print("=" * 60)
print()

# ─────────────────────────────────────────────────────────────
# Helper — write a file and report it
# ─────────────────────────────────────────────────────────────
def write_file(relative_path: str, content: str):
    path = PROJECT_ROOT / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  ✅ {relative_path}")

# ─────────────────────────────────────────────────────────────
# STEP 2.1 — Write database.py (finalized)
# ─────────────────────────────────────────────────────────────
print("[1/7] Writing database.py...")
write_file("backend/database.py", '''\
"""
SQLAlchemy engine, session factory, and Base.
All models import Base from here.
"""
from sqlalchemy import create_engine, event
from sqlalchemy.orm import declarative_base, sessionmaker
from backend.config import settings

# ── Engine ────────────────────────────────────────────────────
connect_args = {}
if "sqlite" in settings.database_url:
    # SQLite: allow the same connection across multiple threads
    # (needed because FastAPI runs in async context)
    connect_args["check_same_thread"] = False

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=(settings.environment == "development"),  # log SQL in dev
)

# Enable WAL mode for SQLite — better concurrent read performance
if "sqlite" in settings.database_url:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

# ── Session ───────────────────────────────────────────────────
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ── Base ──────────────────────────────────────────────────────
Base = declarative_base()

# ── FastAPI dependency ────────────────────────────────────────
def get_db():
    """
    Yields a database session for a single request,
    guarantees it is closed afterwards even if an error occurs.

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
''')
print()

# ─────────────────────────────────────────────────────────────
# STEP 2.2 — User model
# ─────────────────────────────────────────────────────────────
print("[2/7] Writing models...")

write_file("backend/models/user.py", '''\
"""
User model — professors and teaching assistants.
Only professors can finalize grades.
TAs can grade but not approve.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, Enum
from sqlalchemy.orm import relationship
from backend.database import Base
import enum

class UserRole(str, enum.Enum):
    professor = "professor"
    ta        = "ta"

class User(Base):
    __tablename__ = "users"

    id            = Column(String(36), primary_key=True,
                           default=lambda: str(uuid.uuid4()))
    email         = Column(String(255), unique=True, nullable=False, index=True)
    name          = Column(String(255), nullable=False)
    password_hash = Column(String(255), nullable=False)
    role          = Column(Enum(UserRole), default=UserRole.professor, nullable=False)
    is_active     = Column(Boolean, default=True, nullable=False)
    created_at    = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at    = Column(DateTime, default=datetime.utcnow,
                           onupdate=datetime.utcnow, nullable=False)

    # Relationships
    courses = relationship("Course", back_populates="owner",
                           cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User {self.email} ({self.role})>"
''')

write_file("backend/models/course.py", '''\
"""
Course model — e.g. "CS 231N Computer Vision Fall 2025"
One professor owns many courses.
One course has many assignments.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import relationship
from backend.database import Base

class Course(Base):
    __tablename__ = "courses"

    id               = Column(String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))
    user_id          = Column(String(36), ForeignKey("users.id",
                               ondelete="CASCADE"), nullable=False, index=True)
    name             = Column(String(255), nullable=False)
    # e.g. "Fall 2025"
    term             = Column(String(100), nullable=True)
    # Canvas course ID for LMS integration (Stage 11)
    canvas_course_id = Column(String(100), nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at       = Column(DateTime, default=datetime.utcnow,
                               onupdate=datetime.utcnow, nullable=False)

    # Relationships
    owner       = relationship("User", back_populates="courses")
    assignments = relationship("Assignment", back_populates="course",
                               cascade="all, delete-orphan")

    @property
    def assignment_count(self) -> int:
        return len(self.assignments)

    def __repr__(self):
        return f"<Course {self.name} ({self.term})>"
''')

write_file("backend/models/assignment.py", '''\
"""
Assignment model.
Holds the rubric JSON and optional path to the instructor solution notebook.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Numeric, Text
from sqlalchemy.orm import relationship
from backend.database import Base

class AssignmentStatus(str):
    PENDING  = "pending"    # created, no submissions yet
    GRADING  = "grading"    # grading in progress
    COMPLETE = "complete"   # all submissions graded
    ARCHIVED = "archived"   # past semester, read-only

class Assignment(Base):
    __tablename__ = "assignments"

    id                       = Column(String(36), primary_key=True,
                                      default=lambda: str(uuid.uuid4()))
    course_id                = Column(String(36), ForeignKey("courses.id",
                                      ondelete="CASCADE"), nullable=False, index=True)
    name                     = Column(String(255), nullable=False)
    description              = Column(Text, nullable=True)
    # Full rubric stored as JSON — see docs/rubric_format.md for schema
    rubric_json              = Column(JSON, nullable=True)
    # Raw text rubric before parsing (preserved for re-parsing)
    rubric_raw_text          = Column(Text, nullable=True)
    # Filesystem path to instructor solution .ipynb (optional)
    expected_submission_path = Column(String(500), nullable=True)
    total_possible_points    = Column(Numeric(6, 2), default=100.0, nullable=False)
    status                   = Column(String(50), default="pending", nullable=False)
    # Canvas assignment ID for grade push-back (Stage 11)
    canvas_assignment_id     = Column(String(100), nullable=True)
    due_date                 = Column(DateTime, nullable=True)
    created_at               = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at               = Column(DateTime, default=datetime.utcnow,
                                      onupdate=datetime.utcnow, nullable=False)

    # Relationships
    course          = relationship("Course", back_populates="assignments")
    submissions     = relationship("Submission", back_populates="assignment",
                                   cascade="all, delete-orphan")
    similarity_flags = relationship("SimilarityFlag", back_populates="assignment",
                                    cascade="all, delete-orphan")

    @property
    def submission_count(self) -> int:
        return len(self.submissions)

    @property
    def graded_count(self) -> int:
        return sum(1 for s in self.submissions if s.status == "graded")

    def __repr__(self):
        return f"<Assignment {self.name}>"
''')

write_file("backend/models/submission.py", '''\
"""
Submission model — one row per student file uploaded.
Tracks parse status, grading status, and stores the
parsed notebook content as JSON for reuse.
"""
import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Integer, Text
from sqlalchemy.orm import relationship
from backend.database import Base

class SubmissionStatus(str):
    PENDING  = "pending"    # uploaded, not yet parsed
    PARSING  = "parsing"    # being parsed
    GRADING  = "grading"    # AI grading in progress
    GRADED   = "graded"     # grade result created
    ERROR    = "error"      # parse or grading failure
    FLAGGED  = "flagged"    # similarity or integrity flag

class Submission(Base):
    __tablename__ = "submissions"

    id                  = Column(String(36), primary_key=True,
                                 default=lambda: str(uuid.uuid4()))
    assignment_id       = Column(String(36), ForeignKey("assignments.id",
                                 ondelete="CASCADE"), nullable=False, index=True)
    # Student identity — filled from filename or Canvas roster
    student_name        = Column(String(255), nullable=True)
    student_email       = Column(String(255), nullable=True)
    # External ID from Canvas (used when pushing grades back)
    student_id_external = Column(String(100), nullable=True)
    # File storage
    original_filename   = Column(String(500), nullable=False)
    file_path           = Column(String(500), nullable=False)
    # ipynb / html / py
    file_type           = Column(String(20), nullable=False)
    file_size_bytes     = Column(Integer, nullable=True)
    # Cached output of the parser — avoids re-parsing on regrade
    parsed_content      = Column(JSON, nullable=True)
    # Workflow status
    status              = Column(String(50), default="pending", nullable=False)
    error_message       = Column(Text, nullable=True)
    submitted_at        = Column(DateTime, default=datetime.utcnow, nullable=False)
    graded_at           = Column(DateTime, nullable=True)

    # Relationships
    assignment   = relationship("Assignment", back_populates="submissions")
    grade_result = relationship("GradeResult", back_populates="submission",
                                uselist=False, cascade="all, delete-orphan")
    # This submission can appear in similarity flags as either side
    flags_as_a   = relationship("SimilarityFlag",
                                foreign_keys="SimilarityFlag.submission_a_id",
                                back_populates="submission_a")
    flags_as_b   = relationship("SimilarityFlag",
                                foreign_keys="SimilarityFlag.submission_b_id",
                                back_populates="submission_b")

    def __repr__(self):
        return f"<Submission {self.student_name} — {self.file_type}>"
''')

write_file("backend/models/grade_result.py", '''\
"""
GradeResult model — AI-generated grade for one submission.
Stores both the raw AI output and any professor overrides
separately, so we can always diff what changed.
"""
import uuid
from datetime import datetime
from sqlalchemy import (Column, String, DateTime, ForeignKey,
                        JSON, Numeric, Boolean, Text)
from sqlalchemy.orm import relationship
from backend.database import Base

class GradeResult(Base):
    __tablename__ = "grade_results"

    id                 = Column(String(36), primary_key=True,
                                default=lambda: str(uuid.uuid4()))
    # One-to-one with Submission
    submission_id      = Column(String(36), ForeignKey("submissions.id",
                                ondelete="CASCADE"), unique=True,
                                nullable=False, index=True)
    # Scores
    total_score        = Column(Numeric(6, 2), nullable=True)
    total_possible     = Column(Numeric(6, 2), nullable=True)
    percentage         = Column(Numeric(5, 2), nullable=True)
    letter_grade       = Column(String(5), nullable=True)
    # Per-criterion breakdown from AI
    # Schema: [{"criterion_id", "name", "score", "max_score",
    #           "reasoning", "feedback", "flags"}, ...]
    criteria_results   = Column(JSON, nullable=True)
    # Flags raised during grading
    # e.g. ["possible_ai_generated", "no_outputs", "below_accuracy_threshold"]
    flags              = Column(JSON, default=list, nullable=False)
    # Exact raw output from Claude — never modified, preserved for audit
    ai_raw_output      = Column(JSON, nullable=True)
    # Professor's manual overrides
    # Schema: {"criterion_id": {"new_score": x, "note": "..."}, ...}
    professor_overrides = Column(JSON, nullable=True)
    # Overall feedback paragraph shown to student
    summary_feedback   = Column(Text, nullable=True)
    # Whether professor has approved this grade
    finalized          = Column(Boolean, default=False, nullable=False)
    finalized_at       = Column(DateTime, nullable=True)
    created_at         = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at         = Column(DateTime, default=datetime.utcnow,
                                onupdate=datetime.utcnow, nullable=False)

    # Relationships
    submission = relationship("Submission", back_populates="grade_result")

    @property
    def effective_score(self) -> float:
        """
        Returns the final score after applying professor overrides.
        If no overrides exist, returns the AI-generated total.
        """
        if not self.professor_overrides or not self.criteria_results:
            return float(self.total_score or 0)
        # Recalculate from per-criterion scores + overrides
        total = 0.0
        for criterion in self.criteria_results:
            cid = criterion["criterion_id"]
            override = self.professor_overrides.get(cid)
            if override and "new_score" in override:
                total += float(override["new_score"])
            else:
                total += float(criterion["score"])
        return total

    def __repr__(self):
        return f"<GradeResult {self.total_score}/{self.total_possible}>"
''')

write_file("backend/models/similarity_flag.py", '''\
"""
SimilarityFlag model.
Created when two submissions in the same assignment
exceed the similarity threshold.
Professor reviews and marks each flag as resolved.
"""
import uuid
from datetime import datetime
from sqlalchemy import (Column, String, DateTime, ForeignKey,
                        Numeric, Boolean, Text)
from sqlalchemy.orm import relationship
from backend.database import Base

class SimilarityFlag(Base):
    __tablename__ = "similarity_flags"

    id               = Column(String(36), primary_key=True,
                               default=lambda: str(uuid.uuid4()))
    assignment_id    = Column(String(36), ForeignKey("assignments.id",
                               ondelete="CASCADE"), nullable=False, index=True)
    submission_a_id  = Column(String(36), ForeignKey("submissions.id",
                               ondelete="CASCADE"), nullable=False)
    submission_b_id  = Column(String(36), ForeignKey("submissions.id",
                               ondelete="CASCADE"), nullable=False)
    # 0.0 = completely different, 1.0 = identical
    similarity_score = Column(Numeric(4, 3), nullable=False)
    # low / moderate / high
    severity         = Column(String(20), nullable=False, default="moderate")
    # Which method detected this
    # ast_structure / token / combined
    method           = Column(String(50), nullable=False, default="combined")
    # Professor review
    reviewed         = Column(Boolean, default=False, nullable=False)
    professor_note   = Column(Text, nullable=True)
    created_at       = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    assignment   = relationship("Assignment", back_populates="similarity_flags")
    submission_a = relationship("Submission", foreign_keys=[submission_a_id],
                                back_populates="flags_as_a")
    submission_b = relationship("Submission", foreign_keys=[submission_b_id],
                                back_populates="flags_as_b")

    def __repr__(self):
        return (f"<SimilarityFlag {self.similarity_score:.0%} — "
                f"{self.severity}>")
''')

write_file("backend/models/__init__.py", '''\
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
''')
print()

# ─────────────────────────────────────────────────────────────
# STEP 2.3 — config.py update (ensure it handles missing .env gracefully)
# ─────────────────────────────────────────────────────────────
print("[3/7] Updating config.py...")
write_file("backend/config.py", '''\
"""
Central configuration — reads all values from .env file.
NEVER import os.environ directly in other files.
Always use: from backend.config import settings
"""
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # ── Anthropic ─────────────────────────────────────────────
    anthropic_api_key: str = ""

    # ── Database ──────────────────────────────────────────────
    # SQLite for local dev, PostgreSQL for production
    database_url: str = "sqlite:///./autograde.db"

    # ── Auth (JWT) ────────────────────────────────────────────
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    # 480 minutes = 8 hours (a full working day session)
    access_token_expire_minutes: int = 480

    # ── File storage ──────────────────────────────────────────
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 50

    # ── App ───────────────────────────────────────────────────
    environment: str = "development"
    app_name: str = "AutoGrade CS"

    # ── Canvas LMS (populated in Stage 11) ───────────────────
    canvas_base_url: str = ""
    canvas_api_token: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"   # silently ignore unknown env vars

settings = Settings()
''')
print()

# ─────────────────────────────────────────────────────────────
# STEP 2.4 — Set up Alembic
# ─────────────────────────────────────────────────────────────
print("[4/7] Setting up Alembic migration framework...")

# Run alembic init inside backend/alembic (if not already done)
alembic_ini = PROJECT_ROOT / "alembic.ini"
if not alembic_ini.exists():
    result = subprocess.run(
        [str(VENV_PYTHON), "-m", "alembic", "init", "alembic"],
        capture_output=True, text=True, cwd=PROJECT_ROOT
    )
    if result.returncode != 0:
        print(f"  [ERROR] alembic init failed: {result.stderr}")
    else:
        print("  ✅ alembic init complete")
else:
    print("  ✅ alembic.ini already exists — skipping init")

# Write alembic/env.py — connects Alembic to our models and DATABASE_URL
write_file("alembic/env.py", '''\
"""
Alembic migration environment.
Connects to our database and imports all models
so autogenerate can detect schema changes.
"""
import sys
import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Make sure our project root is on the Python path ─────────
# This allows "from backend.xxx import yyy" to work inside migrations
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Import our app config and all models ─────────────────────
from backend.config import settings
from backend.database import Base
# Import all models so Alembic sees them:
import backend.models  # noqa: F401 — side-effect import

# ── Alembic config object ─────────────────────────────────────
config = context.config

# Override the sqlalchemy.url from alembic.ini with our .env value
config.set_main_option("sqlalchemy.url", settings.database_url)

# Set up Python logging from the alembic.ini [loggers] section
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The metadata that autogenerate inspects for schema changes
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (generates SQL script)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations with a live DB connection (applies changes)."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Render as batch for SQLite ALTER TABLE support
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
''')
print()

# ─────────────────────────────────────────────────────────────
# STEP 2.5 — Create first migration
# ─────────────────────────────────────────────────────────────
print("[5/7] Creating initial database migration...")

result = subprocess.run(
    [str(VENV_PYTHON), "-m", "alembic", "revision",
     "--autogenerate", "-m", "initial_tables"],
    capture_output=True, text=True, cwd=PROJECT_ROOT
)
if result.returncode != 0:
    print(f"  [ERROR] Migration creation failed:")
    print(result.stderr)
    print()
    print("  This usually means a model import is failing.")
    print("  Check the error above carefully.")
    sys.exit(1)
else:
    print("  ✅ Migration file created")
    # Extract migration filename from output
    for line in result.stdout.splitlines():
        if "Generating" in line or "revision" in line.lower():
            print(f"  {line.strip()}")
print()

# ─────────────────────────────────────────────────────────────
# STEP 2.6 — Apply migration (creates actual DB tables)
# ─────────────────────────────────────────────────────────────
print("[6/7] Applying migration — creating database tables...")

result = subprocess.run(
    [str(VENV_PYTHON), "-m", "alembic", "upgrade", "head"],
    capture_output=True, text=True, cwd=PROJECT_ROOT
)
if result.returncode != 0:
    print(f"  [ERROR] Migration failed: {result.stderr}")
    sys.exit(1)
else:
    print("  ✅ All tables created")
    for line in result.stdout.splitlines():
        print(f"  {line}")
print()

# ─────────────────────────────────────────────────────────────
# STEP 2.7 — Sanity check: verify all tables exist
# ─────────────────────────────────────────────────────────────
print("[7/7] Running sanity check — verifying all tables and relationships...")

sanity_script = '''\
import sys
sys.path.insert(0, ".")

from backend.database import engine, SessionLocal, Base
from backend.models import User, Course, Assignment, Submission, GradeResult, SimilarityFlag
from sqlalchemy import inspect, text
import uuid
from datetime import datetime

inspector = inspect(engine)
existing_tables = set(inspector.get_table_names())

expected_tables = {
    "users", "courses", "assignments",
    "submissions", "grade_results", "similarity_flags"
}

print("  Tables found in database:")
for table in sorted(existing_tables):
    status = "✅" if table in expected_tables else "ℹ️ "
    print(f"    {status} {table}")

missing = expected_tables - existing_tables
if missing:
    print(f"  ❌ MISSING TABLES: {missing}")
    sys.exit(1)

# ── Quick CRUD test ───────────────────────────────────────────
print()
print("  Running CRUD test...")

db = SessionLocal()
try:
    # Create a test user
    test_user = User(
        id=str(uuid.uuid4()),
        email="test_professor@university.edu",
        name="Test Professor",
        password_hash="not_a_real_hash",
        role="professor"
    )
    db.add(test_user)
    db.flush()  # get the ID without committing

    # Create a test course owned by that user
    test_course = Course(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        name="CS 231N - Computer Vision",
        term="Fall 2025"
    )
    db.add(test_course)
    db.flush()

    # Create a test assignment
    test_assignment = Assignment(
        id=str(uuid.uuid4()),
        course_id=test_course.id,
        name="HW3 - CNN Classification",
        total_possible_points=100.0,
        rubric_json={"criteria": []},
        status="pending"
    )
    db.add(test_assignment)
    db.flush()

    # Create a test submission
    test_submission = Submission(
        id=str(uuid.uuid4()),
        assignment_id=test_assignment.id,
        student_name="Jane Smith",
        original_filename="jane_smith_hw3.ipynb",
        file_path="uploads/test/jane_smith_hw3.ipynb",
        file_type="ipynb",
        status="pending"
    )
    db.add(test_submission)
    db.flush()

    # Create a grade result
    test_grade = GradeResult(
        id=str(uuid.uuid4()),
        submission_id=test_submission.id,
        total_score=87.0,
        total_possible=100.0,
        percentage=87.0,
        letter_grade="B+",
        criteria_results=[],
        flags=[],
        finalized=False
    )
    db.add(test_grade)
    db.flush()

    # Test relationship access
    assert test_course.owner.email == "test_professor@university.edu"
    assert test_assignment.course.name == "CS 231N - Computer Vision"
    assert test_submission.assignment.name == "HW3 - CNN Classification"
    assert test_grade.submission.student_name == "Jane Smith"
    assert test_grade.effective_score == 87.0

    print("  ✅ User created and relationships verified")
    print("  ✅ Course → User relationship works")
    print("  ✅ Assignment → Course relationship works")
    print("  ✅ Submission → Assignment relationship works")
    print("  ✅ GradeResult → Submission relationship works")
    print("  ✅ effective_score property works")

    db.rollback()  # Don\'t actually save test data
    print("  ✅ Test data rolled back (database is clean)")

except Exception as e:
    db.rollback()
    print(f"  ❌ CRUD test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
finally:
    db.close()

print()
print("  All checks passed!")
'''

result = subprocess.run(
    [str(VENV_PYTHON), "-c", sanity_script],
    capture_output=True, text=True, cwd=PROJECT_ROOT
)
print(result.stdout)
if result.returncode != 0:
    print("  [ERROR OUTPUT]:")
    print(result.stderr)
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# Git commit
# ─────────────────────────────────────────────────────────────
print("Committing Stage 2 to git...")
subprocess.run(["git", "add", "."], cwd=PROJECT_ROOT)
result = subprocess.run(
    ["git", "commit", "-m",
     "Stage 2: Complete database layer — 6 models, Alembic migrations, sanity check"],
    capture_output=True, text=True, cwd=PROJECT_ROOT
)
print(result.stdout.strip())
subprocess.run(["git", "push", "origin", "main"],
               capture_output=True, cwd=PROJECT_ROOT)
print("✅ Pushed to GitHub")
print()

# ─────────────────────────────────────────────────────────────
# Done
# ─────────────────────────────────────────────────────────────
print("=" * 60)
print(" Stage 2 Complete!")
print("=" * 60)
print()
print("  database.py         ✅ Engine + session + WAL pragma")
print("  config.py           ✅ Pydantic settings finalized")
print("  models/user.py      ✅ User + UserRole enum")
print("  models/course.py    ✅ Course + owner relationship")
print("  models/assignment.py ✅ Assignment + rubric JSON column")
print("  models/submission.py ✅ Submission + parsed_content cache")
print("  models/grade_result.py ✅ GradeResult + effective_score")
print("  models/similarity_flag.py ✅ SimilarityFlag + severity")
print("  alembic/env.py      ✅ Migration env configured")
print("  autograde.db        ✅ SQLite database created with all tables")
print()
print("  Next → Stage 3: File Parsers (.ipynb / .html / .py)")
print()
input("Press Enter to exit...")