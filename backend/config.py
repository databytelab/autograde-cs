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

    # ── LLM provider selection ────────────────────────────────
    # Which AI backend grades submissions. One of: "openai", "anthropic",
    # "local". Everything else (upload, parsing, similarity, export) works
    # regardless of this value.
    llm_provider: str = "openai"

    # ── OpenAI (default provider) ─────────────────────────────
    openai_api_key: str = ""
    # Leave blank for the real OpenAI API. Set it to point at any
    # OpenAI-compatible gateway (Azure OpenAI, OpenRouter, etc.).
    openai_base_url: str = ""
    openai_grading_model: str = "gpt-4o"
    openai_rubric_model: str = "gpt-4o-mini"

    # ── Local models (OpenAI-compatible: vLLM, Ollama, LM Studio) ──
    # A local server that speaks the OpenAI API. Point this at your Qwen
    # (or any) model. Ollama:    http://localhost:11434/v1
    #                  vLLM:      http://localhost:8000/v1
    #                  LM Studio: http://localhost:1234/v1
    local_base_url: str = "http://localhost:11434/v1"
    # Most local servers ignore the key but the client still needs a value.
    local_api_key: str = "not-needed"
    local_model: str = "qwen2.5-coder:7b"

    # ── Anthropic Claude ──────────────────────────────────────
    anthropic_api_key: str = ""
    anthropic_grading_model: str = "claude-opus-5"
    anthropic_rubric_model: str = "claude-opus-5"

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
    # Echo every SQL statement to the log. Off by default: it is a heavy
    # per-query I/O cost and floods the log. Turn on only to debug queries.
    sql_echo: bool = False

    # ── Canvas LMS (populated in Stage 11) ───────────────────
    canvas_base_url: str = ""
    canvas_api_token: str = ""

    # -- Convenience helpers -----------------------------------
    def active_provider(self) -> str:
        """The provider name, normalised to lowercase."""
        return (self.llm_provider or "openai").strip().lower()

    def grading_configured(self) -> bool:
        """
        True when the *active* provider has what it needs to grade.

        A placeholder value (anything starting with 'your_') counts as not
        configured, so a freshly-copied .env does not look ready.
        """
        provider = self.active_provider()
        if provider == "anthropic":
            key = self.anthropic_api_key
        elif provider == "local":
            # A local server needs a URL, not a real key.
            return bool(self.local_base_url)
        else:  # openai (default) and any OpenAI-compatible gateway
            key = self.openai_api_key
        return bool(key and not key.startswith("your_"))

settings = Settings()
