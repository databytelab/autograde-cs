"""
Rubric engine.

A rubric is the contract between the professor and the grader. It has
exactly one canonical shape in this system:

    {
      "title": "HW3 - Linear Regression",
      "total_points": 100.0,
      "criteria": [
        {
          "id": "c1",
          "name": "Data loading",
          "description": "Reads housing.csv and reports the shape",
          "max_points": 20.0,
          "weight": 1.0,
          "levels": [                     # optional performance bands
            {"label": "Excellent", "points": 20.0, "description": "..."},
            {"label": "Partial",   "points": 10.0, "description": "..."}
          ],
          "keywords": ["read_csv", "shape"],   # optional grep hints
          "requires_output": true              # cell must have been run
        }, ...
      ],
      "grading_notes": "Be generous on style, strict on correctness."
    }

Professors can supply that JSON directly, or paste free text and let
Claude build it. Either way the result goes through `validate_rubric`
before it touches the database.
"""
from __future__ import annotations

import json
import re
from typing import Any

# A criterion cannot be worth negative points, and a rubric with 400
# criteria is a mistake rather than a rubric.
MIN_POINTS = 0.0
MAX_CRITERIA = 60


class RubricError(ValueError):
    """Raised when a rubric cannot be understood or is internally inconsistent."""


# -- Letter grades ----------------------------------------------------
# Standard US scale. Kept here (not in the AI prompt) so the boundary is
# deterministic and identical for every submission.
_LETTER_BANDS: list[tuple[float, str]] = [
    (97, "A+"), (93, "A"), (90, "A-"),
    (87, "B+"), (83, "B"), (80, "B-"),
    (77, "C+"), (73, "C"), (70, "C-"),
    (67, "D+"), (63, "D"), (60, "D-"),
    (0,  "F"),
]


def letter_grade(percentage: float) -> str:
    """Map a 0-100 percentage onto a letter grade."""
    for floor, letter in _LETTER_BANDS:
        if percentage >= floor:
            return letter
    return "F"


# -- Validation / normalisation ---------------------------------------
def _coerce_points(value: Any, field: str, criterion: str) -> float:
    try:
        points = float(value)
    except (TypeError, ValueError):
        raise RubricError(
            f"Criterion '{criterion}': {field} must be a number, got {value!r}"
        ) from None
    if points < MIN_POINTS:
        raise RubricError(f"Criterion '{criterion}': {field} cannot be negative")
    return round(points, 2)


def _slugify(text: str, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return slug[:40] or fallback


def validate_rubric(rubric: dict[str, Any]) -> dict[str, Any]:
    """
    Validate and normalise a rubric dict.

    Returns a NEW normalised dict - the input is never mutated. Fills in
    ids, defaults `weight` to 1.0, and recomputes `total_points` from the
    criteria so the header can never disagree with the body.

    Raises RubricError with a message meant to be shown to the professor.
    """
    if not isinstance(rubric, dict):
        raise RubricError("Rubric must be a JSON object")

    criteria_in = rubric.get("criteria")
    if not isinstance(criteria_in, list) or not criteria_in:
        raise RubricError("Rubric must contain a non-empty 'criteria' list")
    if len(criteria_in) > MAX_CRITERIA:
        raise RubricError(
            f"Rubric has {len(criteria_in)} criteria; the maximum is {MAX_CRITERIA}"
        )

    seen_ids: set[str] = set()
    criteria_out: list[dict[str, Any]] = []

    for position, raw in enumerate(criteria_in, start=1):
        if not isinstance(raw, dict):
            raise RubricError(
                f"Criterion #{position} must be an object, got {type(raw).__name__}"
            )

        name = str(raw.get("name") or "").strip()
        if not name:
            raise RubricError(f"Criterion #{position} is missing a 'name'")

        if "max_points" not in raw:
            raise RubricError(f"Criterion '{name}' is missing 'max_points'")
        max_points = _coerce_points(raw["max_points"], "max_points", name)

        # Ids must be stable and unique - professor overrides are keyed by them.
        cid = str(raw.get("id") or "").strip() or _slugify(name, f"c{position}")
        if cid in seen_ids:
            cid = f"{cid}_{position}"
        seen_ids.add(cid)

        levels_out = []
        for level in raw.get("levels") or []:
            if not isinstance(level, dict):
                raise RubricError(f"Criterion '{name}': each level must be an object")
            level_points = _coerce_points(level.get("points", 0), "level points", name)
            if level_points > max_points:
                raise RubricError(
                    f"Criterion '{name}': level '{level.get('label')}' awards "
                    f"{level_points} points but the criterion caps at {max_points}"
                )
            levels_out.append({
                "label": str(level.get("label") or "").strip() or "Level",
                "points": level_points,
                "description": str(level.get("description") or "").strip(),
            })
        levels_out.sort(key=lambda x: x["points"], reverse=True)

        weight = raw.get("weight", 1.0)
        try:
            weight = round(float(weight), 4)
        except (TypeError, ValueError):
            raise RubricError(f"Criterion '{name}': weight must be a number") from None
        if weight <= 0:
            raise RubricError(f"Criterion '{name}': weight must be greater than 0")

        criteria_out.append({
            "id": cid,
            "name": name,
            "description": str(raw.get("description") or "").strip(),
            "max_points": max_points,
            "weight": weight,
            "levels": levels_out,
            "keywords": [
                str(k).strip() for k in (raw.get("keywords") or []) if str(k).strip()
            ],
            "requires_output": bool(raw.get("requires_output", False)),
        })

    computed_total = round(sum(c["max_points"] for c in criteria_out), 2)
    if computed_total <= 0:
        raise RubricError(
            "Rubric total is 0 points - at least one criterion must be worth points"
        )

    declared = rubric.get("total_points")
    warnings: list[str] = []
    if declared is not None:
        try:
            declared = round(float(declared), 2)
            if abs(declared - computed_total) > 0.01:
                warnings.append(
                    f"Declared total ({declared}) did not match the sum of the "
                    f"criteria ({computed_total}); using {computed_total}."
                )
        except (TypeError, ValueError):
            warnings.append(f"Ignored non-numeric total_points {declared!r}")

    return {
        "title": str(rubric.get("title") or "").strip() or "Untitled rubric",
        "total_points": computed_total,
        "criteria": criteria_out,
        "grading_notes": str(rubric.get("grading_notes") or "").strip(),
        "warnings": warnings,
    }


def criterion_by_id(rubric: dict[str, Any], criterion_id: str) -> dict[str, Any] | None:
    """Look up a single criterion. Returns None if the id is unknown."""
    for criterion in rubric.get("criteria", []):
        if criterion["id"] == criterion_id:
            return criterion
    return None


def rubric_summary(rubric: dict[str, Any]) -> str:
    """One-line human summary, used in logs and the Streamlit UI."""
    n = len(rubric.get("criteria", []))
    return f"{rubric.get('title')} - {n} criteria, {rubric.get('total_points')} points"


# -- Free-text rubrics -------------------------------------------------
def parse_rubric_text(text: str, total_points: float | None = None,
                      provider: Any = None) -> dict[str, Any]:
    """
    Turn a professor's pasted assignment text into a validated rubric.

    Tries, in order:
      1. The text is already rubric JSON  -> validate it directly.
      2. Claude extracts the criteria     -> validate the result.

    The AI call is imported lazily so that importing this module never
    requires an API key (the parsers and the test-suite depend on that).
    """
    if not text or not text.strip():
        raise RubricError("Rubric text is empty")

    stripped = text.strip()

    # 1. Already JSON?
    if stripped.startswith("{"):
        try:
            return validate_rubric(json.loads(stripped))
        except json.JSONDecodeError:
            pass  # fall through to the AI path

    # 2. Ask Claude.
    from backend.ai.grader import extract_rubric_from_text  # local import on purpose

    extracted = extract_rubric_from_text(stripped, total_points=total_points,
                                         provider=provider)
    return validate_rubric(extracted)


def _scale_criteria_to_total(rubric: dict[str, Any], target: float) -> dict[str, Any]:
    """
    Rescale a rubric's criterion points to sum to exactly `target`.

    Models are unreliable at exact arithmetic - asked for 100 points they may
    return criteria summing to 120. We keep the model's *relative* weighting
    but make the totals land on the number the professor asked for, using the
    largest-remainder method so the points stay whole and sum exactly.
    """
    criteria = list(rubric.get("criteria") or [])
    current = sum(float(c.get("max_points", 0) or 0) for c in criteria)
    target_int = int(round(target))
    if not criteria or current <= 0 or target_int <= 0 or abs(current - target) < 0.5:
        return rubric

    factor = target_int / current
    exact = [float(c.get("max_points", 0) or 0) * factor for c in criteria]
    points = [max(1, int(x)) for x in exact]           # floor, at least 1 each

    # Hand out (or claw back) the leftover to the largest fractional parts.
    drift = target_int - sum(points)
    order = sorted(range(len(criteria)), key=lambda i: exact[i] - int(exact[i]),
                   reverse=(drift > 0))
    step = 1 if drift > 0 else -1
    i = 0
    while drift != 0 and order:
        idx = order[i % len(order)]
        if step < 0 and points[idx] <= 1:   # never take a criterion below 1
            i += 1
            if i > len(order) * 3:
                break
            continue
        points[idx] += step
        drift -= step
        i += 1

    scaled = [dict(c, max_points=p) for c, p in zip(criteria, points)]
    out = dict(rubric)
    out["criteria"] = scaled
    out["total_points"] = float(sum(points))
    return out


def build_rubric_from_solution(
    parsed: dict[str, Any],
    total_points: float | None = None,
    instructions: str | None = None,
    provider: Any = None,
) -> dict[str, Any]:
    """
    Turn a parsed instructor solution into a validated rubric.

    The model reads the worked solution and derives criteria that judge the
    underlying work rather than an exact match, since student code and output
    legitimately vary. `instructions` is optional free text from the
    professor - anything the solution file cannot show on its own - and
    takes priority over what the model would otherwise infer. When a total
    is requested, the criterion points are rescaled to sum to it exactly.
    The AI call is imported lazily so importing this module never requires
    an API key.
    """
    from backend.ai.grader import extract_rubric_from_solution  # local import

    extracted = extract_rubric_from_solution(parsed, total_points=total_points,
                                             instructions=instructions,
                                             provider=provider)
    if total_points:
        extracted = _scale_criteria_to_total(extracted, total_points)
    return validate_rubric(extracted)


def build_default_rubric(total_points: float = 100.0) -> dict[str, Any]:
    """
    A generic CS-assignment rubric, used when a professor uploads
    submissions before writing a rubric of their own.
    """
    share = round(total_points / 4, 2)
    remainder = round(total_points - share * 3, 2)
    return validate_rubric({
        "title": "Default CS assignment rubric",
        "criteria": [
            {"id": "correctness", "name": "Correctness",
             "description": "The code produces the correct result for the stated task.",
             "max_points": remainder, "requires_output": True},
            {"id": "completeness", "name": "Completeness",
             "description": "Every part of the assignment is attempted.",
             "max_points": share},
            {"id": "code_quality", "name": "Code quality",
             "description": "Readable names, sensible structure, no dead code.",
             "max_points": share},
            {"id": "explanation", "name": "Explanation",
             "description": "Written reasoning explains what the code does and why.",
             "max_points": share},
        ],
        "grading_notes": "Auto-generated rubric - replace with your own for better results.",
    })
