"""
Anthropic Claude provider.

This is the original grading path, unchanged in behaviour: one structured
`messages.create` call with adaptive thinking, effort control, and a cached
system prompt. It deliberately still pulls its client from
`grader.get_client()` so the existing test suite — which patches that
function — keeps working untouched.
"""
from __future__ import annotations

from typing import Any

import anthropic

from backend.ai.providers.base import GradingError, LLMProvider, extract_json
from backend.config import settings

# Claude structured-output responses fit comfortably; the same ceiling the
# app has always used.
MAX_TOKENS = 16_000


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def _model_for(self, purpose: str) -> str:
        if purpose == "rubric":
            return settings.anthropic_rubric_model
        return settings.anthropic_grading_model

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
        # Late import: grader owns the cached Anthropic client (and the tests
        # patch it there). Importing at module top would create a cycle.
        from backend.ai import grader

        content: list[dict[str, Any]] = []
        for image in images or []:
            content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["media_type"],
                    "data": image["data_b64"],
                },
            })
        content.append({"type": "text", "text": user_prompt})

        client = grader.get_client()
        try:
            response = client.messages.create(
                model=self._model_for(purpose),
                max_tokens=MAX_TOKENS,
                system=[{
                    "type": "text",
                    "text": system,
                    # Byte-identical across a batch, so caching turns the
                    # second and later calls into a cache read.
                    "cache_control": {"type": "ephemeral"},
                }],
                messages=[{"role": "user", "content": content}],
                thinking={"type": "adaptive"},
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": schema},
                },
            )
        except anthropic.AuthenticationError as exc:
            raise GradingError("Anthropic rejected the API key in your .env file.") from exc
        except anthropic.RateLimitError as exc:
            raise GradingError(
                "Anthropic rate limit reached. Wait a moment and grade again."
            ) from exc
        except anthropic.APIStatusError as exc:
            raise GradingError(
                f"Anthropic API error {exc.status_code}: {exc.message}"
            ) from exc
        except anthropic.APIConnectionError as exc:
            raise GradingError(
                "Could not reach the Anthropic API - check your network."
            ) from exc

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            category = getattr(detail, "category", None) if detail else None
            raise GradingError(
                f"Claude declined to grade this submission (category: {category})."
            )
        if response.stop_reason == "max_tokens":
            raise GradingError(
                "The grading response was cut off before it finished. "
                "The submission is probably too large to grade in one pass."
            )

        text = "".join(b.text for b in response.content if b.type == "text")
        if not text.strip():
            raise GradingError("Claude returned an empty response.")

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "cache_read_input_tokens": getattr(
                response.usage, "cache_read_input_tokens", 0
            ),
            "cache_creation_input_tokens": getattr(
                response.usage, "cache_creation_input_tokens", 0
            ),
            "model": response.model,
        }
        return extract_json(text), usage
