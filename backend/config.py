"""
Central configuration — reads all values from .env file.
NEVER import os.environ directly in other files.
Always use: from backend.config import settings
"""
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",       # silently ignore unknown env vars
    )

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

settings = Settings()
