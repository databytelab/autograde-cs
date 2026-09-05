"""
The AI grader — the one place that turns a submission into a grade.

Design rules that the rest of the app depends on, unchanged no matter which
model does the grading (OpenAI, Anthropic, or a local Qwen):

1. **The model never does arithmetic that matters.** The model assigns a
   score per criterion; Python sums them, computes the percentage, and picks
   the letter grade. A model slip cannot corrupt a total.

2. **Every rubric criterion always comes back.** If the model omits one, we
   insert it with a score of 0 and a `grader_error` flag rather than silently
   shrinking the rubric.

3. **Scores are clamped to [0, max_points].** The model cannot award 120 out
   of 20 no matter what it returns.

4. **The raw model output is preserved verbatim** in `ai_raw_output` for the
   audit trail, before any of the above normalisation.

Which model answers is chosen by `settings.llm_provider` and lives behind
`backend.ai.providers`. This module owns the grading *logic*; the provider
owns the *call*.

The Anthropic client is created lazily below (and the test-suite patches it
here), so importing this module never requires an API key — the parsers, the
rubric engine, and most of the test-suite depend on that.
"""
from __future__ import annotations

import logging
from typing import Any

from backend.ai import prompts
from backend.ai.providers import get_provider
# Re-exported so existing imports (`from backend.ai.grader import GradingError`,
# `_extract_json`) keep working now that these live in the provider layer.
from backend.ai.providers.base import GradingError, extract_json as _extract_json
from backend.config import settings
from backend.services.rubric_service import letter_grade

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------
# Anthropic client management
# ---------------------------------------------------------------------
# Kept here (rather than inside the Anthropic provider) so the test-suite,
# which patches `grader.get_client`, keeps working unchanged. The Anthropic
# provider pulls its client from here.
_client: Any = None


def get_client() -> Any:
    """
    Return the shared Anthropic client, creating it on first use.

    `anthropic` is imported here rather than at module scope so that an
    OpenAI-only (or local-model-only) deployment does not have to install it
    just to import the grader. Importing it at the top made the whole API
    refuse to start when the package was absent, which is the opposite of
    what a provider abstraction is for.

    Tests monkeypatch this function (or `backend.ai.grader._client`) to avoid
    any network access.
    """
    global _client
    if _client is None:
        if not settings.anthropic_api_key or settings.anthropic_api_key.startswith("your_"):
            raise GradingError(
                "ANTHROPIC_API_KEY is not set. Add a real key to your .env file "
                "before grading. See .env.example."
            )
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover - only without the package
            raise GradingError(
                "The 'anthropic' package is not installed. Run: pip install anthropic"
            ) from exc
        _client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_max_retries,
        )
    return _client


def reset_client() -> None:
    """Drop the cached client - used by tests and after a config change."""
    global _client
    _client = None


# ---------------------------------------------------------------------
# Normalisation - the trust boundary around the model's output
# ---------------------------------------------------------------------
_KNOWN_FLAGS = {
    "no_outputs", "runtime_error", "incomplete",
    "possible_ai_generated", "output_mismatch",
    # Raised when the submission contains text aimed at the grader rather
    # than at the assignment. Always worth a human look.
    "prompt_injection",
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

    # A model that answered, but about criteria of its own invention. Small
    # local models do this: the response is schema-valid, every criterion_id
    # is made up, so nothing matches and every criterion falls to zero. That
    # is the clamping working, but "everything scored 0" is not a useful
    # thing to hand a professor without saying why - the score is not a
    # judgement of the student at all.
    rubric_criteria = rubric.get("criteria", [])
    returned = len(by_id)
    if rubric_criteria and returned and not (
            by_id.keys() & {c["id"] for c in rubric_criteria}):
        flags.add("rubric_ignored")
        summary = (
            f"The grader replied about {returned} criteria of its own rather "
            f"than the {len(rubric_criteria)} in your rubric, so none of its "
            "scores could be used and everything below is zero. This is "
            "almost always a model that is too small to follow a rubric - "
            "try a larger one under Settings, AI providers. Nothing here "
            "reflects the student's work."
        )
        ai_output = {**ai_output, "summary_feedback": summary}

    # Criterion-level flags that matter at the submission level.
    unknown = {f for f in flags if f not in _KNOWN_FLAGS and f not in
               ("grader_error", "score_clamped", "rubric_ignored")}
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
    provider: Any = None,
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

    # `provider` lets a caller grade with a specific professor's own key
    # (see credential_service.resolve_provider_for_user). When it is None the
    # administrator's server-wide provider is used, which is the default and
    # the only behaviour that existed before BYOK.
    ai_output, usage = (provider or get_provider()).complete_json(
        system=prompts.GRADING_SYSTEM,
        user_prompt=user_prompt,
        schema=prompts.GRADING_RESPONSE_SCHEMA,
        images=images,
        effort="high",
        purpose="grading",
    )

    result = normalize_grade(ai_output, rubric)

    # Deterministic checks the model should not be trusted to make. These are
    # the only automatic flags - both are genuine "look at this" signals:
    # a notebook that was never run, and a recorded runtime error.
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
    provider: Any = None,
) -> dict[str, Any]:
    """
    Ask the model to turn a prose assignment description into rubric JSON.

    Returns the RAW extracted dict - the caller is expected to run it through
    `rubric_service.validate_rubric`.

    `provider` is the professor's own, when they have one. Without it this
    used the server-wide account, so a professor whose only credentials were
    their own could not build a rubric at all - the first thing they do.
    """
    ai_output, _usage = (provider or get_provider()).complete_json(
        system=prompts.RUBRIC_EXTRACTION_SYSTEM,
        user_prompt=prompts.build_rubric_extraction_prompt(text, total_points),
        schema=prompts.RUBRIC_RESPONSE_SCHEMA,
        effort="medium",
        purpose="rubric",
    )
    return ai_output


def extract_rubric_from_solution(
    parsed: dict[str, Any],
    total_points: float | None = None,
    provider: Any = None,
) -> dict[str, Any]:
    """
    Ask the model to build a rubric from an instructor's *worked solution*.

    Reads the parsed solution (code, prose, outputs) and derives grading
    criteria that judge the underlying work rather than an exact code/output
    match - students implement differently and their output legitimately
    varies. Returns the RAW extracted dict; the caller validates it.
    """
    ai_output, _usage = (provider or get_provider()).complete_json(
        system=prompts.RUBRIC_FROM_SOLUTION_SYSTEM,
        user_prompt=prompts.build_rubric_from_solution_prompt(parsed, total_points),
        schema=prompts.RUBRIC_RESPONSE_SCHEMA,
        effort="medium",
        purpose="rubric",
    )
    return ai_output
