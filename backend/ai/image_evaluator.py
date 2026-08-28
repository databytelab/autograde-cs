"""
Figure evaluation.

Plots are the part of a data-science submission that text alone cannot
judge - a student can write flawless matplotlib code and still produce an
unlabelled, misleading chart. This module sends the extracted figures to
Claude's vision input and asks whether they satisfy a specific criterion.

It is deliberately separate from grader.py: the main grading call already
attaches a few figures inline, and this module is for the case where a
professor wants a focused, per-figure judgement.
"""
from __future__ import annotations

from typing import Any

from backend.ai import prompts
from backend.ai.grader import GradingError, _call_claude

# Vision calls are the most expensive thing this app does. Cap them.
MAX_IMAGES_PER_CALL = 4


def evaluate_figures(
    *,
    images: list[dict[str, str]],
    criterion: dict[str, Any],
    context: str = "",
) -> dict[str, Any]:
    """
    Judge one or more figures against a single rubric criterion.

    `images` are entries from a parse result:
        {"cell_index": int, "media_type": "image/png", "data_b64": "..."}

    Returns:
        {"description", "meets_criterion", "issues", "feedback",
         "n_images_evaluated"}
    """
    if not images:
        return {
            "description": "The submission contained no figures.",
            "meets_criterion": False,
            "issues": ["no_figures"],
            "feedback": "This criterion asks for a plot, but none was found "
                        "in your submission.",
            "n_images_evaluated": 0,
        }

    batch = images[:MAX_IMAGES_PER_CALL]
    cells = ", ".join(str(img.get("cell_index")) for img in batch)

    user_prompt = (
        f"# Criterion being assessed\n"
        f"{criterion.get('name')} (worth {criterion.get('max_points')} points)\n"
        f"{criterion.get('description') or ''}\n\n"
        f"# Context\n{context or 'No additional context provided.'}\n\n"
        f"# Figures\n"
        f"{len(batch)} figure(s) from cell(s) {cells} are attached above.\n\n"
        f"# Your task\n"
        f"Describe what the figure(s) show, then judge whether they satisfy "
        f"the criterion."
    )

    result, _usage = _call_claude(
        system=prompts.IMAGE_EVAL_SYSTEM,
        user_prompt=user_prompt,
        schema=prompts.IMAGE_EVAL_SCHEMA,
        model="claude-opus-5",
        images=batch,
        effort="medium",
    )

    return {
        "description": str(result.get("description") or "").strip(),
        "meets_criterion": bool(result.get("meets_criterion")),
        "issues": [str(i) for i in (result.get("issues") or [])],
        "feedback": str(result.get("feedback") or "").strip(),
        "n_images_evaluated": len(batch),
    }


def has_figures(parsed: dict[str, Any]) -> bool:
    """True when a parsed submission contains at least one usable figure."""
    return bool(parsed.get("images"))


__all__ = ["evaluate_figures", "has_figures", "GradingError", "MAX_IMAGES_PER_CALL"]
