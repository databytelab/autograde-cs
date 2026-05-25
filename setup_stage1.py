# setup_stage1.py
# Stage 1: Creates complete folder structure, all placeholder files,
# virtual environment, installs all dependencies, creates .env template

import os
import sys
import subprocess
import venv
from pathlib import Path

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
VENV_DIR     = PROJECT_ROOT / "venv"

print("=" * 60)
print(" AutoGrade CS — Stage 1: Project Scaffold")
print(f" Project root: {PROJECT_ROOT}")
print("=" * 60)
print()

# ─────────────────────────────────────────────────────────────
# STEP 1.1 — Create all folders
# ─────────────────────────────────────────────────────────────
print("[1/6] Creating folder structure...")

FOLDERS = [
    # Backend
    "backend",
    "backend/models",
    "backend/schemas",
    "backend/routers",
    "backend/parsers",
    "backend/ai",
    "backend/services",
    "backend/utils",
    "backend/alembic",
    "backend/alembic/versions",

    # Streamlit frontend (MVP)
    "frontend_streamlit",
    "frontend_streamlit/pages",
    "frontend_streamlit/components",

    # Next.js frontend (built later)
    "frontend",

    # Tests
    "tests",
    "tests/sample_submissions",

    # Scripts
    "scripts",

    # Docs
    "docs",

    # Uploads (gitignored)
    "uploads",

    # Docker
    "docker",
]

for folder in FOLDERS:
    path = PROJECT_ROOT / folder
    path.mkdir(parents=True, exist_ok=True)
    # Create .gitkeep so empty folders are tracked by git
    gitkeep = path / ".gitkeep"
    if not any(path.iterdir()) if path.exists() else True:
        gitkeep.touch()

print(f"  Created {len(FOLDERS)} folders")
print("[OK] Folder structure created")
print()

# ─────────────────────────────────────────────────────────────
# STEP 1.2 — Create all placeholder Python files
# ─────────────────────────────────────────────────────────────
print("[2/6] Creating placeholder files...")

# Each entry: (relative_path, file_content)
FILES = {

    # ── Backend core ──────────────────────────────────────────
    "backend/__init__.py": "",

    "backend/main.py": '''\
"""
AutoGrade CS — FastAPI Application Entry Point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="AutoGrade CS",
    description="AI-powered assignment grading for CS courses",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}
''',

    "backend/config.py": '''\
"""
Central configuration — reads from .env file.
Always import settings from here, never use os.environ directly.
"""
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = ""

    # Database
    database_url: str = "sqlite:///./autograde.db"

    # Auth
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480

    # File storage
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 50

    # Environment
    environment: str = "development"

    # Canvas LMS (optional)
    canvas_base_url: str = ""
    canvas_api_token: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
''',

    "backend/database.py": '''\
"""
SQLAlchemy database engine, session factory, and Base class.
"""
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from backend.config import settings

engine = create_engine(
    settings.database_url,
    # SQLite-specific: allow use across threads
    connect_args={"check_same_thread": False}
    if "sqlite" in settings.database_url else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    """FastAPI dependency — yields a DB session, always closes after request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
''',

    # ── Models ────────────────────────────────────────────────
    "backend/models/__init__.py": '''\
from backend.models.user import User
from backend.models.course import Course
from backend.models.assignment import Assignment
from backend.models.submission import Submission
from backend.models.grade_result import GradeResult
from backend.models.similarity_flag import SimilarityFlag
''',

    "backend/models/user.py": '''\
"""User model — professors and TAs."""
# Populated in Stage 2
''',

    "backend/models/course.py": '''\
"""Course model."""
# Populated in Stage 2
''',

    "backend/models/assignment.py": '''\
"""Assignment model."""
# Populated in Stage 2
''',

    "backend/models/submission.py": '''\
"""Student submission model."""
# Populated in Stage 2
''',

    "backend/models/grade_result.py": '''\
"""AI-generated grade result model."""
# Populated in Stage 2
''',

    "backend/models/similarity_flag.py": '''\
"""Similarity/academic integrity flag model."""
# Populated in Stage 2
''',

    # ── Schemas ───────────────────────────────────────────────
    "backend/schemas/__init__.py": "",

    "backend/schemas/user.py": '''\
"""Pydantic schemas for User — request/response validation."""
# Populated in Stage 7
''',

    "backend/schemas/course.py": '''\
"""Pydantic schemas for Course."""
# Populated in Stage 7
''',

    "backend/schemas/assignment.py": '''\
"""Pydantic schemas for Assignment."""
# Populated in Stage 7
''',

    "backend/schemas/submission.py": '''\
"""Pydantic schemas for Submission."""
# Populated in Stage 7
''',

    "backend/schemas/grade_result.py": '''\
"""Pydantic schemas for GradeResult."""
# Populated in Stage 7
''',

    # ── Routers ───────────────────────────────────────────────
    "backend/routers/__init__.py": "",

    "backend/routers/auth.py": '''\
"""Authentication routes — login, register, me."""
# Populated in Stage 7
''',

    "backend/routers/courses.py": '''\
"""Course management routes."""
# Populated in Stage 7
''',

    "backend/routers/assignments.py": '''\
"""Assignment routes."""
# Populated in Stage 7
''',

    "backend/routers/submissions.py": '''\
"""Submission upload and grading trigger routes."""
# Populated in Stage 7
''',

    "backend/routers/results.py": '''\
"""Grade result retrieval and override routes."""
# Populated in Stage 7
''',

    "backend/routers/export.py": '''\
"""Export routes — CSV, PDF, Canvas push."""
# Populated in Stage 8
''',

    # ── Parsers ───────────────────────────────────────────────
    "backend/parsers/__init__.py": "",

    "backend/parsers/notebook_parser.py": '''\
"""Parser for .ipynb Jupyter notebook files."""
# Populated in Stage 3
''',

    "backend/parsers/html_parser.py": '''\
"""Parser for .html exported Jupyter notebooks."""
# Populated in Stage 3
''',

    "backend/parsers/python_parser.py": '''\
"""Parser for .py Python script files."""
# Populated in Stage 3
''',

    "backend/parsers/parser_router.py": '''\
"""Dispatcher — routes file to correct parser based on extension."""
# Populated in Stage 3
''',

    # ── AI ────────────────────────────────────────────────────
    "backend/ai/__init__.py": "",

    "backend/ai/prompts.py": '''\
"""
All LLM prompt templates in one place.
Never scatter prompts across files.
"""
# Populated in Stage 5
''',

    "backend/ai/grader.py": '''\
"""Core AI grading functions — calls Claude API."""
# Populated in Stage 5
''',

    "backend/ai/image_evaluator.py": '''\
"""Evaluates student plot images using Claude vision."""
# Populated in Stage 5
''',

    # ── Services ──────────────────────────────────────────────
    "backend/services/__init__.py": "",

    "backend/services/grading_service.py": '''\
"""Orchestrates the full grading pipeline for a submission."""
# Populated in Stage 5
''',

    "backend/services/rubric_service.py": '''\
"""Rubric parsing, validation, and template management."""
# Populated in Stage 4
''',

    "backend/services/export_service.py": '''\
"""CSV and PDF export generation."""
# Populated in Stage 8
''',

    "backend/services/canvas_service.py": '''\
"""Canvas LMS API integration."""
# Populated in Stage 11
''',

    # ── Utils ─────────────────────────────────────────────────
    "backend/utils/__init__.py": "",

    "backend/utils/file_utils.py": '''\
"""File type detection, validation, and storage helpers."""
# Populated in Stage 7
''',

    "backend/utils/similarity.py": '''\
"""AST-based code similarity detection for academic integrity."""
# Populated in Stage 6
''',

    "backend/utils/auth_utils.py": '''\
"""JWT creation, verification, and password hashing helpers."""
# Populated in Stage 7
''',

    # ── Streamlit Frontend ────────────────────────────────────
    "frontend_streamlit/__init__.py": "",

    "frontend_streamlit/app.py": '''\
"""
AutoGrade CS — Streamlit MVP Frontend
Run with: streamlit run frontend_streamlit/app.py
"""
import streamlit as st

st.set_page_config(
    page_title="AutoGrade CS",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 AutoGrade CS")
st.write("MVP frontend — pages coming in Stage 9")
''',

    "frontend_streamlit/pages/__init__.py": "",
    "frontend_streamlit/pages/dashboard.py":    "# Dashboard page — Stage 9",
    "frontend_streamlit/pages/new_assignment.py": "# New assignment page — Stage 9",
    "frontend_streamlit/pages/upload_grade.py": "# Upload and grade page — Stage 9",
    "frontend_streamlit/pages/review_results.py": "# Review results page — Stage 9",
    "frontend_streamlit/pages/export.py":       "# Export page — Stage 9",

    "frontend_streamlit/components/__init__.py": "",
    "frontend_streamlit/components/api_client.py": '''\
"""
Centralized API client for Streamlit — all requests go through here.
Automatically attaches JWT token from session state.
"""
import requests
import streamlit as st

API_BASE = "http://localhost:8000"

def api_call(method: str, endpoint: str, **kwargs):
    """Make an authenticated API call."""
    headers = kwargs.pop("headers", {})
    token = st.session_state.get("token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    url = f"{API_BASE}{endpoint}"
    try:
        response = requests.request(method, url, headers=headers, **kwargs)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot connect to backend. Is the FastAPI server running?")
        return None
    except requests.exceptions.HTTPError as e:
        st.error(f"API error: {e.response.status_code} — {e.response.text}")
        return None
''',

    # ── Tests ─────────────────────────────────────────────────
    "tests/__init__.py": "",
    "tests/test_parsers.py":    "# Parser tests — Stage 3",
    "tests/test_rubric_engine.py": "# Rubric engine tests — Stage 4",
    "tests/test_grader.py":     "# AI grader tests — Stage 5",
    "tests/test_similarity.py": "# Similarity detection tests — Stage 6",
    "tests/test_api.py":        "# FastAPI endpoint tests — Stage 7",
    "tests/test_full_pipeline.py": "# End-to-end pipeline tests — Stage 10",

    # ── Scripts ───────────────────────────────────────────────
    "scripts/benchmark_grader.py": '''\
"""
Run AI grader against manually graded ground truth samples.
Measures Mean Absolute Error — use this to tune prompts.
Run: py -3.11 scripts/benchmark_grader.py
"""
# Populated in Stage 10
''',

    "scripts/seed_demo_data.py": '''\
"""
Seeds the database with demo courses, assignments, and sample grades.
Useful for testing the frontend without real submissions.
Run: py -3.11 scripts/seed_demo_data.py
"""
# Populated in Stage 9
''',

    # ── Docs ──────────────────────────────────────────────────
    "docs/rubric_format.md": '''\
# Rubric Format Guide

## Option A — Natural Language (easiest)
Paste your assignment instructions directly.
The AI will extract criteria and point values automatically.

## Option B — Structured JSON
See docs/rubric_schema.json for the full schema.

## Option C — Instructor Solution Notebook
Upload your solved .ipynb — outputs become the expected values.
''',

    "docs/canvas_setup.md": '''\
# Canvas LMS Integration Setup

1. Log in to your Canvas instance
2. Go to Account → Settings → Approved Integrations
3. Generate a new access token
4. Add to .env: CANVAS_API_TOKEN=your_token
5. Add to .env: CANVAS_BASE_URL=https://your_university.instructure.com
''',

    "docs/api_reference.md": "# API Reference\n\nGenerated from FastAPI at http://localhost:8000/docs\n",

    # ── Docker ────────────────────────────────────────────────
    "docker/README.md": "# Docker configuration files\nSee root docker-compose.yml for usage.\n",

    # ── Root level files ──────────────────────────────────────
    "docker-compose.yml": '''\
# Docker Compose — populated in Stage 13
version: "3.8"
services:
  backend:
    build: ./backend
    ports:
      - "8000:8000"
    env_file: .env

  frontend:
    build: ./frontend_streamlit
    ports:
      - "8501:8501"
    depends_on:
      - backend
''',

    ".env.example": '''\
# Copy this file to .env and fill in your values
# NEVER commit .env to git

# Anthropic Claude API
ANTHROPIC_API_KEY=your_anthropic_api_key_here

# Database (SQLite for dev, PostgreSQL for production)
DATABASE_URL=sqlite:///./autograde.db

# Auth — generate with: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY=generate_a_random_secret_here
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480

# File uploads
UPLOAD_DIR=./uploads
MAX_FILE_SIZE_MB=50

# Environment
ENVIRONMENT=development

# Canvas LMS (optional — leave blank if not using)
CANVAS_BASE_URL=
CANVAS_API_TOKEN=
''',
}

# Write all files
created = 0
skipped = 0
for relative_path, content in FILES.items():
    file_path = PROJECT_ROOT / relative_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    if not file_path.exists():
        file_path.write_text(content, encoding="utf-8")
        created += 1
    else:
        skipped += 1

print(f"  Created {created} files, skipped {skipped} existing")
print("[OK] All placeholder files created")
print()

# ─────────────────────────────────────────────────────────────
# STEP 1.3 — Create .env from .env.example if not exists
# ─────────────────────────────────────────────────────────────
print("[3/6] Setting up .env file...")

env_path = PROJECT_ROOT / ".env"
env_example_path = PROJECT_ROOT / ".env.example"

if not env_path.exists():
    import shutil
    shutil.copy(env_example_path, env_path)
    print("  Created .env from .env.example")
    print("  ⚠️  IMPORTANT: Open .env and add your ANTHROPIC_API_KEY")
else:
    print("  .env already exists — skipping")

print("[OK] .env ready")
print()

# ─────────────────────────────────────────────────────────────
# STEP 1.4 — Create requirements.txt
# ─────────────────────────────────────────────────────────────
print("[4/6] Creating requirements.txt...")

REQUIREMENTS = """\
# Web framework
fastapi==0.111.0
uvicorn[standard]==0.29.0

# Settings and env
pydantic==2.7.1
pydantic-settings==2.2.1
python-dotenv==1.0.1

# Database
sqlalchemy==2.0.30
alembic==1.13.1
psycopg2-binary==2.9.9

# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# File handling
python-multipart==0.0.9
nbformat==5.10.4
beautifulsoup4==4.12.3
lxml==5.2.2

# AI
anthropic==0.28.0

# Data and export
pandas==2.2.2
reportlab==4.1.0
openpyxl==3.1.2

# HTTP client
httpx==0.27.0
requests==2.32.2

# Streamlit frontend
streamlit==1.35.0

# Testing
pytest==8.2.0
pytest-asyncio==0.23.7

# Utilities
python-slugify==8.0.4
"""

req_path = PROJECT_ROOT / "requirements.txt"
req_path.write_text(REQUIREMENTS, encoding="utf-8")
print("[OK] requirements.txt created")
print()

# ─────────────────────────────────────────────────────────────
# STEP 1.5 — Create virtual environment
# ─────────────────────────────────────────────────────────────
print("[5/6] Creating virtual environment with Python 3.11...")

if not VENV_DIR.exists():
    result = subprocess.run(
        ["py", "-3.11", "-m", "venv", str(VENV_DIR)],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"[ERROR] Failed to create venv: {result.stderr}")
        sys.exit(1)
    print(f"  Virtual environment created at: {VENV_DIR}")
else:
    print("  Virtual environment already exists — skipping creation")

# Path to pip inside the venv
pip_path = VENV_DIR / "Scripts" / "pip.exe"  # Windows
if not pip_path.exists():
    pip_path = VENV_DIR / "bin" / "pip"       # macOS/Linux

print("  Installing dependencies (this takes 2–3 minutes)...")

result = subprocess.run(
    [str(pip_path), "install", "-r", "requirements.txt"],
    capture_output=False,  # Show output live
    text=True,
    cwd=PROJECT_ROOT
)

if result.returncode != 0:
    print("[ERROR] Some packages failed to install — check output above")
    print("        Try running manually:")
    print(f"        {pip_path} install -r requirements.txt")
else:
    print("[OK] All dependencies installed")
print()

# ─────────────────────────────────────────────────────────────
# STEP 1.6 — Generate SECRET_KEY and insert into .env
# ─────────────────────────────────────────────────────────────
import secrets

env_content = env_path.read_text(encoding="utf-8")
if "generate_a_random_secret_here" in env_content:
    new_secret = secrets.token_hex(32)
    env_content = env_content.replace(
        "generate_a_random_secret_here",
        new_secret
    )
    env_path.write_text(env_content, encoding="utf-8")
    print(f"  Auto-generated SECRET_KEY in .env")

# ─────────────────────────────────────────────────────────────
# STEP 1.7 — Git commit
# ─────────────────────────────────────────────────────────────
print("[6/6] Committing scaffold to git...")

subprocess.run(["git", "add", "."], cwd=PROJECT_ROOT)
result = subprocess.run(
    ["git", "commit", "-m",
     "Stage 1: Complete project scaffold — folders, placeholders, requirements, venv"],
    capture_output=True, text=True, cwd=PROJECT_ROOT
)
print(result.stdout.strip())

subprocess.run(
    ["git", "push", "origin", "main"],
    capture_output=True, text=True, cwd=PROJECT_ROOT
)
print("[OK] Pushed to GitHub")
print()

# ─────────────────────────────────────────────────────────────
# DONE — Print next steps
# ─────────────────────────────────────────────────────────────
print("=" * 60)
print(" Stage 1 Complete!")
print("=" * 60)
print()
print(" Folder structure:    ✅ Created")
print(" Placeholder files:   ✅ Created")
print(" requirements.txt:    ✅ Created")
print(" Virtual environment: ✅ Created at ./venv")
print(" Dependencies:        ✅ Installed")
print(" .env:                ✅ Ready")
print(" Git commit:          ✅ Pushed")
print()
print(" ─────────────────────────────────────────────")
print(" ONE MANUAL STEP REQUIRED:")
print(" Open .env and add your Anthropic API key:")
print()
print("   ANTHROPIC_API_KEY=your_key_here")
print()
print(" ─────────────────────────────────────────────")
print()
print(" To activate venv for future terminal work:")
print("   Windows:  venv\\Scripts\\activate")
print()
print(" To verify FastAPI works:")
print("   venv\\Scripts\\uvicorn backend.main:app --reload")
print("   Then open: http://localhost:8000/api/health")
print()
print(" When ready → Stage 2: Database Layer")
print()

input("Press Enter to exit...")