"""
OpenAI-compatible provider.

Drives any server that speaks the OpenAI Chat Completions API. That covers:

  * OpenAI itself (the default backend),
  * OpenAI-compatible gateways (Azure OpenAI, OpenRouter, ...),
  * local model servers — vLLM, Ollama, LM Studio — which is how a local
    Qwen model is graded with no code change, only a different base URL.

The same class backs both the "openai" and "local" providers; the factory in
`__init__.py` constructs it with the right key/URL/model for each.

Structured outputs: we ask for a strict JSON schema, which OpenAI honours
exactly. Smaller local servers may not implement strict schemas, so we fall
back to plain JSON mode and lean on `extract_json` — the grader's trust
boundary re-checks everything either way.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.ai.providers.base import GradingError, LLMProvider, extract_json
from backend.config import settings

try:  # openai is an optional dependency until a provider actually needs it
    import openai
except ImportError:  # pragma: no cover - exercised only without the package
    openai = None  # type: ignore

logger = logging.getLogger(__name__)

MAX_TOKENS = 16_000

# Used whenever no gateway URL is configured.
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"


def make_client(api_key: str, base_url: str | None,
                timeout: float | None = None):
    """
    Build an OpenAI client. Isolated in a module function so tests can patch
    it with a fake without any network access.

    Timeout and retries are set explicitly: the SDK's 600s default is long
    enough that a single stalled request holds up every submission behind it
    in a batch. The SDK retries 429s and 5xx with exponential backoff.

    `timeout` overrides the configured one. A hosted API answers in seconds;
    a 7B model on a laptop without a graphics card takes minutes, and the
    120s that suits OpenAI made every local grading run fail.
    """
    if openai is None:
        raise GradingError(
            "The 'openai' package is not installed. Run: pip install openai"
        )
    # base_url is always passed explicitly, never left to the SDK.
    #
    # When it is omitted the SDK falls back to reading OPENAI_BASE_URL from
    # the process environment - and .env ships that key blank. Under Docker
    # `env_file` puts the blank value into the real environment, so the SDK
    # built a URL with no scheme and every grading call failed with
    # "Connection error" / UnsupportedProtocol. It never showed up in local
    # development because pydantic-settings reads .env without exporting it.
    kwargs: dict[str, Any] = {
        "api_key": api_key or "not-needed",
        "timeout": timeout or settings.llm_timeout_seconds,
        "max_retries": settings.llm_max_retries,
        "base_url": (base_url or "").strip() or DEFAULT_OPENAI_BASE_URL,
    }
    return openai.OpenAI(**kwargs)


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        api_key: str,
        base_url: str | None,
        grading_model: str,
        rubric_model: str,
        reasoning_effort: str | None = None,
    ) -> None:
        self.name = name
        self._api_key = api_key
        self._base_url = base_url or None
        self._grading_model = grading_model
        self._rubric_model = rubric_model
        # Set for reasoning models (o-series / gpt-5); left None for gpt-4o
        # and most local models, which reject the parameter.
        self._reasoning_effort = reasoning_effort
        self._client = None

    def _get_client(self):
        if self._client is None:
            if self.name == "openai" and not (
                self._api_key and not self._api_key.startswith("your_")
            ):
                raise GradingError(
                    "No OpenAI key is set up. Add one under "
                    "Settings -> AI providers, then try again."
                )
            self._client = make_client(self._api_key, self._base_url,
                                       timeout=self._timeout())
        return self._client

    def _model_for(self, purpose: str) -> str:
        return self._rubric_model if purpose == "rubric" else self._grading_model

    def _build_messages(
        self, system: str, user_prompt: str, images: list[dict[str, str]] | None
    ) -> list[dict[str, Any]]:
        if images:
            content: list[dict[str, Any]] = [{"type": "text", "text": user_prompt}]
            for image in images:
                data_uri = f"data:{image['media_type']};base64,{image['data_b64']}"
                content.append({"type": "image_url", "image_url": {"url": data_uri}})
            user_content: Any = content
        else:
            # A plain string is friendlier to text-only local models.
            user_content = user_prompt
        return [
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ]

    def _base_kwargs(self, model: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": model, "messages": messages}
        if self._reasoning_effort:
            kwargs["reasoning_effort"] = self._reasoning_effort
            kwargs["max_completion_tokens"] = MAX_TOKENS
        else:
            kwargs["max_tokens"] = MAX_TOKENS
            kwargs["temperature"] = 0  # grading should be as repeatable as possible
        return kwargs

    def complete_json(
        self,
        *,
        system: str,
        user_prompt: str,
        schema: dict[str, Any],
        images: list[dict[str, str]] | None = None,
        effort: str = "high",
        purpose: str = "grading",
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        client = self._get_client()
        model = self._model_for(purpose)
        messages = self._build_messages(system, user_prompt, images)
        kwargs = self._base_kwargs(model, messages)

        strict_format = {
            "type": "json_schema",
            "json_schema": {"name": "response", "schema": schema, "strict": True},
        }

        try:
            response = self._create(client, {**kwargs, "response_format": strict_format})
        except openai.BadRequestError as exc:
            # A local server that does not support strict JSON schemas. Retry
            # in plain JSON mode; extract_json + the grader's normalisation
            # still guarantee a sound result.
            logger.info(
                "Strict JSON schema rejected by %s (%s); retrying in json_object mode.",
                self.name, getattr(exc, "message", exc),
            )
            try:
                response = self._create(
                    client, {**kwargs, "response_format": {"type": "json_object"}}
                )
            except openai.BadRequestError:
                # Some minimal servers support no response_format at all.
                response = self._create(client, kwargs)

        choice = response.choices[0]
        finish = getattr(choice, "finish_reason", None)
        if finish == "length":
            raise GradingError(
                "The grading response was cut off before it finished. "
                "The submission is probably too large to grade in one pass."
            )
        if finish == "content_filter":
            raise GradingError(
                f"The model declined to grade this submission (content filter)."
            )

        text = choice.message.content or ""
        if not text.strip():
            raise GradingError(f"The model ({self.name}) returned an empty response.")

        usage = self._usage(response)
        return extract_json(text), usage

    def _timeout(self) -> float:
        """
        How long to wait for an answer.

        A local model runs on the professor's own computer, where a single
        submission can genuinely take several minutes. The hosted default
        is far too short for that, so local gets its own, longer limit.
        """
        if self.name == "local":
            return float(settings.local_timeout_seconds)
        return float(settings.llm_timeout_seconds)

    def _create(self, client, kwargs: dict[str, Any]):
        """One call, with provider error types translated to GradingError."""
        try:
            return client.chat.completions.create(**kwargs)
        except openai.AuthenticationError as exc:
            raise GradingError(
                f"{self.name} rejected this API key. Check it under "
                "Settings -> AI providers, or replace it with a new one."
            ) from exc
        except openai.RateLimitError as exc:
            raise GradingError(
                f"{self.name} rate limit reached. Wait a moment and grade again."
            ) from exc
        except openai.APITimeoutError as exc:
            # Caught before APIConnectionError, which is its parent class.
            # Without this, a local model that is simply slow reported
            # "could not reach the server" and sent the professor hunting a
            # networking problem that was not there.
            raise GradingError(
                f"The {self.name} model did not answer within "
                f"{self._timeout():.0f} seconds. "
                + ("A local model on a computer without a graphics card can "
                   "be this slow. Try a smaller model, or raise "
                   "LLM_TIMEOUT_SECONDS."
                   if self.name == "local" else
                   "The service may be overloaded - try again shortly.")
            ) from exc
        except openai.APIConnectionError as exc:
            # The most common local-model failure: the server is not running.
            raise GradingError(
                f"Could not reach the {self.name} server"
                + (f" at {self._base_url}" if self._base_url else "")
                + " - check that it is running and the base URL is correct."
            ) from exc
        except openai.BadRequestError:
            raise  # handled by the caller (schema fallback)
        except openai.APIStatusError as exc:
            raise GradingError(
                f"{self.name} API error {exc.status_code}: {getattr(exc, 'message', exc)}"
            ) from exc

    @staticmethod
    def _usage(response) -> dict[str, Any]:
        u = getattr(response, "usage", None)
        if u is None:
            return {
                "input_tokens": 0, "output_tokens": 0,
                "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0,
                "model": getattr(response, "model", "unknown"),
            }
        details = getattr(u, "prompt_tokens_details", None)
        cached = getattr(details, "cached_tokens", 0) if details else 0
        return {
            "input_tokens": getattr(u, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(u, "completion_tokens", 0) or 0,
            "cache_read_input_tokens": cached or 0,
            "cache_creation_input_tokens": 0,
            "model": getattr(response, "model", "unknown"),
        }
