"""
The AI grader - the one place that talks to Claude about grading.

Design rules that the rest of the app depends on:

1. **The model never does arithmetic that matters.** Claude assigns a
   score per criterion; Python sums them, computes the percentage, and
   picks the letter grade. A model slip cannot corrupt a total.

2. **Every rubric criterion always comes back.** If the model omits one,
   we insert it with a score of 0 and a `grader_error` flag rather than
   silently shrinking the rubric.

3. **Scores are clamped to [0, max_points].** The model cannot award 120
   out of 20 no matter what it returns.

4. **The raw model output is preserved verbatim** in `ai_raw_output` for
   the audit trail, before any of the above normalisation.

The client is created lazily, so importing this module never requires an
API key - the parsers, the rubric engine and most of the test-suite
depend on that.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from backend.ai import prompts
from backend.config import settings
from backend.services.rubric_service import letter_grade

logger = logging.getLogger(__name__)

# Grading is the quality-critical path: use the strongest model.
GRADING_MODEL = "claude-opus-5"
# Rubric extraction is a smaller, more mechanical job but still benefits
# from careful reading of the professor's prose.
RUBRIC_MODEL = "claude-opus-5"

MAX_TOKENS = 16_000

_client: anthropic.Anthropic | None = None


class GradingError(RuntimeError):
    """Raised when the AI grader cannot produce a usable result."""


def get_client() -> anthropic.Anthropic:
    """
    Return the shared Anthropic client, creating it on first use.

    Tests monkeypatch this function (or `backend.ai.grader._client`) to
    avoid any network access.
    """
    global _client
    if _client is None:
        if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("your_"):
            raise GradingError(
                "ANTHROPIC_API_KEY is not set. Add a real key to your .env file "
                "before grading. See .env.example."
            )
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client


def reset_client() -> None:
    """Drop the cached client - used by tests and after a config change."""
    global _client
    _client = None


# ---------------------------------------------------------------------
# Low-level call
# ---------------------------------------------------------------------
_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.M)


def _extract_json(text: str) -> dict[str, Any]:
    """
    Parse the model's response into a dict.

    Structured outputs make the response pure JSON, but we stay tolerant
    of a stray markdown fence or a leading sentence so that a transient
    formatting slip does not fail a whole batch.
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


def _call_claude(
    *,
    system: str,
    user_prompt: str,
    schema: dict[str, Any],
    model: str,
    images: list[dict[str, str]] | None = None,
    effort: str = "high",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """
    One structured-output call to Claude.

    Returns (parsed_json, usage_info). Raises GradingError on refusal,
    truncation, or unparseable output.
    """
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

    client = get_client()
    try:
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=[{
                "type": "text",
                "text": system,
                # The system prompt is byte-identical for every submission
                # in a batch, so caching it turns the second and later
                # calls into a cache read.
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
        raise GradingError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
    except anthropic.APIConnectionError as exc:
        raise GradingError("Could not reach the Anthropic API - check your network.") from exc

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
        "cache_read_input_tokens": getattr(response.usage, "cache_read_input_tokens", 0),
        "cache_creation_input_tokens": getattr(
            response.usage, "cache_creation_input_tokens", 0
        ),
        "model": response.model,
    }
    return _extract_json(text), usage


# ---------------------------------------------------------------------
# Normalisation - the trust boundary around the model's output
# ---------------------------------------------------------------------
_KNOWN_FLAGS = {
    "no_outputs", "runtime_error", "incomplete",
    "possible_ai_generated", "output_mismatch",
}


def _clean_flags(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return sorted({
        str(f).strip().lower().replace(" ", "_")
        for f in raw
        if str(f).strip()
    })


def normalize_grade(
    ai_output: dict[str, Any],
    rubric: dict[str, Any],
) -> dict[str, Any]:
    """
    Turn raw model output into the GradeResult payload.

    This is where we stop trusting the model: scores get clamped, missing
    criteria get filled in, and every total is recomputed in Python.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for item in ai_output.get("criteria_results") or []:
        if isinstance(item, dict) and item.get("criterion_id"):
            by_id[str(item["criterion_id"])] = item

    criteria_results: list[dict[str, Any]] = []
    flags: set[str] = set(_clean_flags(ai_output.get("overall_flags")))
    total = 0.0

    for criterion in rubric.get("criteria", []):
        cid = criterion["id"]
        max_points = float(criterion["max_points"])
        item = by_id.get(cid)

        if item is None:
            # The model skipped this criterion entirely.
            criteria_results.append({
                "criterion_id": cid,
                "name": criterion["name"],
                "score": 0.0,
                "max_score": max_points,
                "reasoning": "The grader did not return a result for this criterion.",
                "feedback": "This criterion could not be graded automatically. "
                            "Please review it manually.",
                "flags": ["grader_error"],
            })
            flags.add("grader_error")
            continue

        try:
            score = float(item.get("score", 0))
        except (TypeError, ValueError):
            score = 0.0
            flags.add("grader_error")

        # Clamp: the model may not award more than the rubric allows.
        clamped = max(0.0, min(score, max_points))
        item_flags = _clean_flags(item.get("flags"))
        if abs(clamped - score) > 0.001:
            item_flags.append("score_clamped")
            flags.add("score_clamped")

        criteria_results.append({
            "criterion_id": cid,
            "name": criterion["name"],
            "score": round(clamped, 2),
            "max_score": max_points,
            "reasoning": str(item.get("reasoning") or "").strip(),
            "feedback": str(item.get("feedback") or "").strip(),
            "flags": sorted(set(item_flags)),
        })
        flags.update(item_flags)
        total += clamped

    total_possible = float(rubric.get("total_points") or 0.0)
    total = round(total, 2)
    percentage = round(total / total_possible * 100, 2) if total_possible else 0.0

    # Criterion-level flags that matter at the submission level.
    unknown = {f for f in flags if f not in _KNOWN_FLAGS and f not in
               ("grader_error", "score_clamped")}
    if unknown:
        logger.info("Grader produced non-standard flags: %s", sorted(unknown))

    return {
        "total_score": total,
        "total_possible": round(total_possible, 2),
        "percentage": percentage,
        "letter_grade": letter_grade(percentage),
        "criteria_results": criteria_results,
        "flags": sorted(flags),
        "summary_feedback": str(ai_output.get("summary_feedback") or "").strip(),
    }


# ---------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------
def grade_submission(
    *,
    parsed: dict[str, Any],
    rubric: dict[str, Any],
    assignment_name: str,
    assignment_description: str | None = None,
    expected_solution: dict[str, Any] | None = None,
    include_images: bool = True,
    max_images: int = 4,
) -> dict[str, Any]:
    """
    Grade one parsed submission against one validated rubric.

    Returns the GradeResult payload:
        total_score, total_possible, percentage, letter_grade,
        criteria_results, flags, summary_feedback, ai_raw_output, usage
    """
    if not rubric.get("criteria"):
        raise GradingError("Cannot grade against a rubric with no criteria")

    user_prompt = prompts.build_grading_user_prompt(
        assignment_name=assignment_name,
        assignment_description=assignment_description,
        rubric=rubric,
        parsed=parsed,
        expected_solution=expected_solution,
    )

    images = []
    if include_images:
        # Figures are expensive; send only the first few.
        images = (parsed.get("images") or [])[:max_images]

    ai_output, usage = _call_claude(
        system=prompts.GRADING_SYSTEM,
        user_prompt=user_prompt,
        schema=prompts.GRADING_RESPONSE_SCHEMA,
        model=GRADING_MODEL,
        images=images,
    )

    result = normalize_grade(ai_output, rubric)

    # Deterministic checks the model should not be trusted to make.
    stats = parsed.get("stats") or {}
    if stats.get("n_code_cells") and not stats.get("has_outputs"):
        if "no_outputs" not in result["flags"]:
            result["flags"] = sorted(set(result["flags"]) | {"no_outputs"})
    if parsed.get("errors"):
        result["flags"] = sorted(set(result["flags"]) | {"runtime_error"})

    result["ai_raw_output"] = ai_output
    result["usage"] = usage
    return result


def extract_rubric_from_text(
    text: str,
    total_points: float | None = None,
) -> dict[str, Any]:
    """
    Ask Claude to turn a prose assignment description into rubric JSON.

    Returns the RAW extracted dict - the caller is expected to run it
    through `rubric_service.validate_rubric`.
    """
    ai_output, _usage = _call_claude(
        system=prompts.RUBRIC_EXTRACTION_SYSTEM,
        user_prompt=prompts.build_rubric_extraction_prompt(text, total_points),
        schema=prompts.RUBRIC_RESPONSE_SCHEMA,
        model=RUBRIC_MODEL,
        effort="medium",
    )
    return ai_output
