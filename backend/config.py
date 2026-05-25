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
