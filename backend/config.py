"""
Central configuration — reads all values from .env file.
NEVER import os.environ directly in other files.
Always use: from backend.config import settings
"""
from typing import ClassVar

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

    # ── LLM call limits ───────────────────────────────────────
    # Both SDKs default to a 600s timeout, which is far too long inside a
    # batch: one hung request stalls every submission behind it. Retries are
    # made explicit here rather than inherited from an SDK default, so the
    # behaviour is visible and tunable.
    llm_timeout_seconds: float = 120.0
    llm_max_retries: int = 3

    # ── Database ──────────────────────────────────────────────
    # SQLite for local dev, PostgreSQL for production
    database_url: str = "sqlite:///./autograde.db"

    # ── Auth (JWT) ────────────────────────────────────────────
    # This default is a development convenience and is refused outside
    # development by `assert_production_ready()`. Anyone who knows it can
    # mint a valid token for any account, so it must never ship.
    secret_key: str = "change-this-in-production"
    algorithm: str = "HS256"
    # 480 minutes = 8 hours (a full working day session)
    access_token_expire_minutes: int = 480

    # ── File storage ──────────────────────────────────────────
    upload_dir: str = "./uploads"
    max_file_size_mb: int = 50

    # Blanket cap on any request body, enforced by middleware. Larger than
    # max_file_size_mb so a legitimate multi-file upload still fits, and
    # matched by the reverse proxy's own limit.
    max_request_body_mb: int = 300

    # Origins allowed to call the API from a browser. Comma-separated.
    # The Streamlit frontend calls the API server-side, so this matters only
    # for direct browser access (Swagger, a future JS client).
    cors_origins: str = "http://localhost:8501,http://localhost:3000"

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
    # The signing key shipped in .env.example / as the field default. Running
    # with it means every issued JWT can be forged by anyone with the source.
    DEFAULT_SECRET_KEY: ClassVar[str] = "change-this-in-production"
    MIN_SECRET_KEY_LENGTH: ClassVar[int] = 32
    DEFAULT_DATABASE_URL: ClassVar[str] = "sqlite:///./autograde.db"
    # Placeholder values .env.example ships. Any of them means "not filled in".
    PLACEHOLDER_MARKERS: ClassVar[tuple[str, ...]] = (
        "your_", "change_me", "change-me", "generate_a_random", "placeholder",
    )

    def is_production(self) -> bool:
        return self.environment.strip().lower() in ("production", "prod", "staging")

    def is_testing(self) -> bool:
        return self.environment.strip().lower() in ("test", "testing")

    def assert_production_ready(self) -> list[str]:
        """
        Refuse to start a non-development deployment with an unsafe secret,
        and return any non-fatal warnings for the caller to log.

        The split is deliberate. A forgeable signing key is a security hole
        with no legitimate use, so it fails the boot - a silently insecure
        production process is far worse than a refused start. SQLite, by
        contrast, is a reasonable choice for a single-instance deployment on
        a persistent disk, so it warns rather than blocks.

        Development keeps the convenient defaults and is never checked.
        """
        if not self.is_production():
            return []

        problems: list[str] = []

        if self.secret_key == self.DEFAULT_SECRET_KEY:
            problems.append(
                "SECRET_KEY is still the built-in default, so anyone with the "
                "source can mint a token for any account. Generate one with "
                "`python -c \"import secrets; print(secrets.token_urlsafe(48))\"`"
            )
        elif len(self.secret_key) < self.MIN_SECRET_KEY_LENGTH:
            problems.append(
                f"SECRET_KEY is shorter than {self.MIN_SECRET_KEY_LENGTH} "
                "characters and is too easy to brute-force."
            )
        elif self._is_placeholder(self.secret_key):
            problems.append(
                "SECRET_KEY still holds the placeholder from .env.example."
            )

        # SQLite is fine for development and for the test-suite, but a
        # production deployment runs an API and a worker as separate
        # processes against the same database. SQLite serialises writers and
        # `FOR UPDATE SKIP LOCKED` does not exist there, so job claiming
        # degrades to a lock-step queue - and on ephemeral container storage
        # the whole gradebook disappears on redeploy.
        if self.database_url == self.DEFAULT_DATABASE_URL:
            problems.append(
                "DATABASE_URL is still the development default "
                f"({self.DEFAULT_DATABASE_URL}). Set a PostgreSQL URL."
            )
        elif self.database_url.startswith("sqlite"):
            problems.append(
                "DATABASE_URL points at SQLite. Production runs the API and "
                "the grading worker as separate processes; use PostgreSQL so "
                "job claiming is transactional and the data survives a "
                "redeploy."
            )
        elif self._is_placeholder(self.database_url):
            problems.append("DATABASE_URL still holds a placeholder value.")

        # The provider that will actually be used must be configured, and
        # not with the example placeholder.
        if not self.grading_configured():
            problems.append(
                f"The '{self.active_provider()}' provider has no usable "
                "credentials, so grading would fail for every submission."
            )

        if problems:
            raise ValueError(
                f"Refusing to start in environment '{self.environment}':\n  - "
                + "\n  - ".join(problems)
            )

        warnings: list[str] = []
        if not self.canvas_base_url:
            warnings.append(
                "Canvas is not configured; grades can still be exported as "
                "CSV/Excel/PDF but cannot be pushed to the gradebook."
            )
        return warnings

    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list, ignoring blanks and stray whitespace."""
        return [o.strip() for o in (self.cors_origins or "").split(",") if o.strip()]

    def _is_placeholder(self, value: str) -> bool:
        lowered = (value or "").lower()
        return any(marker in lowered for marker in self.PLACEHOLDER_MARKERS)

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
