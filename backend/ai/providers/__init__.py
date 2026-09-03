"""
Provider factory.

`get_provider()` returns the LLM backend named by `settings.llm_provider`.
The instance is cached, but the cache is keyed on the provider name, so
flipping `LLM_PROVIDER` (or a test monkeypatching it) transparently rebuilds
the right one.
"""
from __future__ import annotations

from backend.ai.providers.base import GradingError, LLMProvider
from backend.config import settings

_provider: LLMProvider | None = None
_provider_key: str | None = None


def _build(name: str) -> LLMProvider:
    if name == "anthropic":
        from backend.ai.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider()

    from backend.ai.providers.openai_provider import OpenAICompatibleProvider

    if name == "local":
        return OpenAICompatibleProvider(
            name="local",
            api_key=settings.local_api_key,
            base_url=settings.local_base_url,
            grading_model=settings.local_model,
            rubric_model=settings.local_model,
        )

    # Default: OpenAI (also handles any unrecognised value, and any
    # OpenAI-compatible gateway reached via openai_base_url).
    return OpenAICompatibleProvider(
        name="openai",
        api_key=settings.openai_api_key,
        base_url=settings.openai_base_url or None,
        grading_model=settings.openai_grading_model,
        rubric_model=settings.openai_rubric_model,
    )


def get_provider() -> LLMProvider:
    """Return the active provider, building (or rebuilding) it as needed."""
    global _provider, _provider_key
    name = settings.active_provider()
    if _provider is None or _provider_key != name:
        _provider = _build(name)
        _provider_key = name
    return _provider


def reset_provider() -> None:
    """Drop the cached provider — used by tests and after a config change."""
    global _provider, _provider_key
    _provider = None
    _provider_key = None


__all__ = ["get_provider", "reset_provider", "LLMProvider", "GradingError"]
