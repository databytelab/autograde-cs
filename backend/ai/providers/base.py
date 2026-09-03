"""
The provider abstraction — one interface, several LLM backends.

Every backend (OpenAI, Anthropic, a local OpenAI-compatible server) speaks
the *same* small contract to the rest of the app:

    provider.complete_json(system=..., user_prompt=..., schema=...) -> (dict, usage)

The grader builds a system prompt, a per-submission user prompt, a JSON
schema, and optional figures. The provider turns that into a structured
call to its model and hands back a parsed dict plus a usage summary. Nothing
above this layer knows or cares which model answered.

`GradingError` and `extract_json` live here (not in grader.py) so that every
provider can raise/parse the same way without importing the grader, which
would create an import cycle.
"""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any


class GradingError(RuntimeError):
    """Raised when an LLM provider cannot produce a usable result."""


# A markdown fence the model sometimes wraps its JSON in, despite being told
# not to. Strip it before parsing.
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.M)


def extract_json(text: str) -> dict[str, Any]:
    """
    Parse a model's response into a dict.

    Structured outputs make the response pure JSON, but we stay tolerant of a
    stray markdown fence or a leading sentence so that a transient formatting
    slip (common with smaller local models) does not fail a whole batch.
    """
    candidate = _FENCE.sub("", text).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass

    # Fall back to the outermost {...} span.
    start, end = candidate.find("{"), candidate.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(candidate[start : end + 1])
        except json.JSONDecodeError as exc:
            raise GradingError(
                f"Model returned text that is not valid JSON: {exc}"
            ) from exc
    raise GradingError("Model returned no JSON object at all")


class LLMProvider(ABC):
    """
    The one thing every AI backend must be able to do: take a prompt plus a
    JSON schema and return a parsed object.

    `purpose` lets a provider pick the right model for the job without the
    caller having to know model names:
        "grading"  the main, quality-critical call (also used for figures)
        "rubric"   turning prose into a rubric — smaller, more mechanical
    """

    name: str = "base"

    @abstractmethod
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
        """
        Return (parsed_json, usage_info).

        `images` are parse-result figures: {"media_type", "data_b64", ...}.
        Raises GradingError on refusal, truncation, or unparseable output.
        """
        raise NotImplementedError
