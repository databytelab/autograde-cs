"""Rubric engine tests - Stage 4.

The rubric is the contract the grader is held to, so validation has to be
strict and its error messages have to be readable by a professor.
"""
from __future__ import annotations

import pytest

from backend.services.rubric_service import (
    MAX_CRITERIA,
    RubricError,
    build_default_rubric,
    criterion_by_id,
    letter_grade,
    parse_rubric_text,
    rubric_summary,
    validate_rubric,
)


# ---------------------------------------------------------------------
# Letter grades
# ---------------------------------------------------------------------
@pytest.mark.parametrize("percentage,expected", [
    (100, "A+"), (97, "A+"), (96.9, "A"), (93, "A"), (92.9, "A-"),
    (90, "A-"), (89.9, "B+"), (83, "B"), (80, "B-"), (77, "C+"),
    (73, "C"), (70, "C-"), (67, "D+"), (63, "D"), (60, "D-"),
    (59.9, "F"), (0, "F"),
])
def test_letter_grade_boundaries(percentage, expected):
    assert letter_grade(percentage) == expected


def test_letter_grade_handles_over_100():
    """Extra credit must not fall off the end of the scale."""
    assert letter_grade(105) == "A+"


# ---------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------
def test_valid_rubric_is_normalised():
    rubric = validate_rubric({
        "title": "  HW3  ",
        "criteria": [
            {"name": "Correctness", "max_points": "60"},
            {"name": "Style", "max_points": 40, "weight": "2"},
        ],
    })
    assert rubric["title"] == "HW3"
    assert rubric["total_points"] == 100.0
    assert rubric["criteria"][0]["id"] == "correctness"
    assert rubric["criteria"][0]["max_points"] == 60.0  # coerced from str
    assert rubric["criteria"][1]["weight"] == 2.0
    # defaults are filled in
    assert rubric["criteria"][0]["levels"] == []
    assert rubric["criteria"][0]["requires_output"] is False


def test_total_points_is_recomputed_not_trusted():
    rubric = validate_rubric({
        "total_points": 999,
        "criteria": [{"name": "A", "max_points": 10},
                     {"name": "B", "max_points": 15}],
    })
    assert rubric["total_points"] == 25.0
    assert rubric["warnings"]
    assert "999" in rubric["warnings"][0]


def test_duplicate_ids_are_disambiguated():
    rubric = validate_rubric({"criteria": [
        {"name": "Part A", "max_points": 10},
        {"name": "Part A", "max_points": 10},
    ]})
    ids = [c["id"] for c in rubric["criteria"]]
    assert len(set(ids)) == 2, "criterion ids must be unique"


def test_input_is_not_mutated():
    original = {"criteria": [{"name": "A", "max_points": 10}]}
    snapshot = {"criteria": [{"name": "A", "max_points": 10}]}
    validate_rubric(original)
    assert original == snapshot


def test_levels_are_sorted_high_to_low():
    rubric = validate_rubric({"criteria": [{
        "name": "A", "max_points": 10,
        "levels": [
            {"label": "Poor", "points": 2},
            {"label": "Great", "points": 10},
            {"label": "OK", "points": 6},
        ],
    }]})
    points = [level["points"] for level in rubric["criteria"][0]["levels"]]
    assert points == [10.0, 6.0, 2.0]


@pytest.mark.parametrize("bad,message", [
    ("not a dict", "must be a JSON object"),
    ({}, "non-empty 'criteria' list"),
    ({"criteria": []}, "non-empty 'criteria' list"),
    ({"criteria": ["nope"]}, "must be an object"),
    ({"criteria": [{"max_points": 10}]}, "missing a 'name'"),
    ({"criteria": [{"name": "A"}]}, "missing 'max_points'"),
    ({"criteria": [{"name": "A", "max_points": "abc"}]}, "must be a number"),
    ({"criteria": [{"name": "A", "max_points": -5}]}, "cannot be negative"),
    ({"criteria": [{"name": "A", "max_points": 0}]}, "total is 0 points"),
    ({"criteria": [{"name": "A", "max_points": 5, "weight": 0}]},
     "greater than 0"),
    ({"criteria": [{"name": "A", "max_points": 5, "weight": "x"}]},
     "weight must be a number"),
    ({"criteria": [{"name": "A", "max_points": 5,
                    "levels": [{"label": "L", "points": 9}]}]},
     "caps at 5.0"),
    ({"criteria": [{"name": "A", "max_points": 5, "levels": ["no"]}]},
     "level must be an object"),
])
def test_invalid_rubrics_are_rejected_with_a_readable_message(bad, message):
    with pytest.raises(RubricError, match=message):
        validate_rubric(bad)


def test_too_many_criteria_rejected():
    criteria = [{"name": f"C{i}", "max_points": 1} for i in range(MAX_CRITERIA + 1)]
    with pytest.raises(RubricError, match="maximum is"):
        validate_rubric({"criteria": criteria})


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def test_build_default_rubric_sums_exactly():
    for total in (100, 50, 33, 7):
        rubric = build_default_rubric(total)
        assert rubric["total_points"] == float(total)
        assert sum(c["max_points"] for c in rubric["criteria"]) == float(total)


def test_criterion_by_id():
    rubric = build_default_rubric(100)
    assert criterion_by_id(rubric, "correctness")["name"] == "Correctness"
    assert criterion_by_id(rubric, "nonexistent") is None


def test_rubric_summary_is_one_line():
    summary = rubric_summary(build_default_rubric(100))
    assert "\n" not in summary
    assert "4 criteria" in summary
    assert "100" in summary


# ---------------------------------------------------------------------
# Free-text rubrics
# ---------------------------------------------------------------------
def test_parse_rubric_text_accepts_raw_json_without_calling_the_ai():
    """JSON in, JSON out - no API key required for this path."""
    rubric = parse_rubric_text(
        '{"title": "From JSON", "criteria": '
        '[{"name": "A", "max_points": 40}, {"name": "B", "max_points": 60}]}'
    )
    assert rubric["title"] == "From JSON"
    assert rubric["total_points"] == 100.0


def test_parse_rubric_text_rejects_empty():
    with pytest.raises(RubricError, match="empty"):
        parse_rubric_text("   ")


def test_parse_rubric_text_calls_the_ai_for_prose(mock_claude):
    fake = mock_claude({
        "title": "HW3",
        "total_points": 100,
        "criteria": [
            {"id": "a", "name": "Load data", "description": "Read the CSV",
             "max_points": 40, "keywords": ["read_csv"], "requires_output": True},
            {"id": "b", "name": "Fit model", "description": "OLS",
             "max_points": 60, "keywords": [], "requires_output": False},
        ],
        "grading_notes": "",
    })

    rubric = parse_rubric_text(
        "Load housing.csv, then fit a linear regression and report R-squared.",
        total_points=100,
    )

    assert rubric["total_points"] == 100.0
    assert [c["id"] for c in rubric["criteria"]] == ["a", "b"]
    assert len(fake.calls) == 1
    # the extraction call must use a JSON schema, not free-form text
    assert fake.calls[0]["output_config"]["format"]["type"] == "json_schema"


def test_ai_extracted_rubric_is_still_validated(mock_claude):
    """A model that returns a bad rubric must not poison the database."""
    mock_claude({"title": "Bad", "total_points": 100,
                 "criteria": [{"id": "a", "name": "", "description": "",
                               "max_points": 10, "keywords": [],
                               "requires_output": False}],
                 "grading_notes": ""})
    with pytest.raises(RubricError, match="missing a 'name'"):
        parse_rubric_text("Some prose that will produce a bad rubric.")


# ---------------------------------------------------------------------
# Rescaling a solution-derived rubric to the requested total
# ---------------------------------------------------------------------
def test_scale_criteria_to_total_hits_the_target_exactly():
    from backend.services.rubric_service import _scale_criteria_to_total

    rubric = {"criteria": [
        {"id": "a", "name": "A", "max_points": 20},
        {"id": "b", "name": "B", "max_points": 25},
        {"id": "c", "name": "C", "max_points": 25},
        {"id": "d", "name": "D", "max_points": 10},
        {"id": "e", "name": "E", "max_points": 25},
        {"id": "f", "name": "F", "max_points": 15},
    ]}  # sums to 120
    scaled = _scale_criteria_to_total(rubric, 100)
    points = [c["max_points"] for c in scaled["criteria"]]
    assert sum(points) == 100
    assert all(p >= 1 for p in points)
    # The smallest criterion (D) stays the smallest after scaling.
    assert scaled["criteria"][3]["max_points"] == min(points)


def test_scale_criteria_leaves_a_matching_total_alone():
    from backend.services.rubric_service import _scale_criteria_to_total

    rubric = {"criteria": [{"id": "a", "name": "A", "max_points": 60},
                           {"id": "b", "name": "B", "max_points": 40}]}
    scaled = _scale_criteria_to_total(rubric, 100)
    assert [c["max_points"] for c in scaled["criteria"]] == [60, 40]
