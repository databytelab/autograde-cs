"""AI grader tests - Stage 5.

No test here touches the network. The point of these tests is the trust
boundary in `normalize_grade`: whatever the model returns, the grade that
reaches the database must be arithmetically sound and rubric-bounded.
"""
from __future__ import annotations

import anthropic
import pytest

from backend.ai import prompts
from backend.ai.grader import (
    GradingError,
    _extract_json,
    extract_rubric_from_text,
    grade_submission,
    normalize_grade,
    reset_client,
)
from backend.parsers import parse_submission
from backend.services.rubric_service import validate_rubric
from tests.conftest import SAMPLES, SIMPLE_RUBRIC, grading_payload


@pytest.fixture
def rubric():
    return validate_rubric(SIMPLE_RUBRIC)


@pytest.fixture
def parsed():
    return parse_submission(SAMPLES / "good_submission.ipynb")


# ---------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------
def test_extract_json_plain():
    assert _extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_strips_markdown_fence():
    assert _extract_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_extract_json_survives_a_leading_sentence():
    assert _extract_json('Here is the result:\n{"a": 1}') == {"a": 1}


def test_extract_json_raises_on_garbage():
    with pytest.raises(GradingError, match="no JSON object"):
        _extract_json("I would rather not.")

    with pytest.raises(GradingError, match="not valid JSON"):
        _extract_json('{"a": 1, this is not valid}')


# ---------------------------------------------------------------------
# normalize_grade - the trust boundary
# ---------------------------------------------------------------------
def test_normalize_computes_totals_in_python(rubric):
    result = normalize_grade(grading_payload(), rubric)
    assert result["total_score"] == 89.0        # 27 + 40 + 22
    assert result["total_possible"] == 100.0
    assert result["percentage"] == 89.0
    assert result["letter_grade"] == "B+"


def test_normalize_caps_feedback_and_summary_length(rubric):
    """
    Student-facing text is capped as a safety net behind the prompt's word
    limits: per-criterion feedback to ~40 words, the summary to ~50, trimmed
    at a sentence boundary so it never cuts a sentence in half.
    """
    long_sentence = ("This is a very wordy sentence that keeps going and going "
                     "with many extra words. " * 6)
    payload = grading_payload()
    for crit in payload["criteria_results"]:
        crit["feedback"] = long_sentence
    payload["summary_feedback"] = long_sentence

    result = normalize_grade(payload, rubric)
    for crit in result["criteria_results"]:
        assert len(crit["feedback"].split()) <= 40
    assert len(result["summary_feedback"].split()) <= 70


def test_normalize_does_not_cap_the_rubric_ignored_notice(rubric):
    """
    The injected 'the grader ignored your rubric' message must keep its
    fix-it advice, so the 50-word cap must not truncate it.
    """
    payload = grading_payload()
    # criterion ids the rubric does not contain -> triggers rubric_ignored
    payload["criteria_results"] = [
        {"criterion_id": "made_up_1", "name": "X", "score": 5, "max_score": 10,
         "reasoning": "", "feedback": "", "flags": []},
    ]
    result = normalize_grade(payload, rubric)
    assert "rubric_ignored" in result["flags"]
    assert "Settings" in result["summary_feedback"]     # advice intact, untrimmed


def test_normalize_ignores_model_arithmetic(rubric):
    """The model claiming a total does not make it so."""
    payload = grading_payload()
    payload["total_score"] = 100          # a lie
    payload["percentage"] = 100           # also a lie
    result = normalize_grade(payload, rubric)
    assert result["total_score"] == 89.0


def test_normalize_clamps_scores_above_max(rubric):
    payload = grading_payload({"loading": 500, "model": 45, "writeup": 25})
    result = normalize_grade(payload, rubric)

    loading = next(c for c in result["criteria_results"]
                   if c["criterion_id"] == "loading")
    assert loading["score"] == 30.0
    assert "score_clamped" in loading["flags"]
    assert "score_clamped" in result["flags"]
    assert result["total_score"] == 100.0


def test_normalize_clamps_negative_scores(rubric):
    payload = grading_payload({"loading": -20, "model": 45, "writeup": 25})
    result = normalize_grade(payload, rubric)
    loading = next(c for c in result["criteria_results"]
                   if c["criterion_id"] == "loading")
    assert loading["score"] == 0.0
    assert result["total_score"] == 70.0


def test_normalize_fills_in_criteria_the_model_skipped(rubric):
    payload = grading_payload()
    payload["criteria_results"] = payload["criteria_results"][:1]  # drop two

    result = normalize_grade(payload, rubric)

    assert len(result["criteria_results"]) == 3, "every criterion must be present"
    missing = [c for c in result["criteria_results"]
               if "grader_error" in c["flags"]]
    assert len(missing) == 2
    assert all(c["score"] == 0.0 for c in missing)
    assert "grader_error" in result["flags"]


def test_normalize_handles_a_completely_empty_response(rubric):
    result = normalize_grade({}, rubric)
    assert result["total_score"] == 0.0
    assert result["letter_grade"] == "F"
    assert len(result["criteria_results"]) == 3
    assert "grader_error" in result["flags"]


def test_normalize_handles_non_numeric_scores(rubric):
    payload = grading_payload()
    payload["criteria_results"][0]["score"] = "twenty-seven"
    result = normalize_grade(payload, rubric)
    assert result["criteria_results"][0]["score"] == 0.0
    assert "grader_error" in result["flags"]


def test_normalize_ignores_criteria_the_rubric_does_not_have(rubric):
    """A hallucinated criterion must not add points."""
    payload = grading_payload()
    payload["criteria_results"].append({
        "criterion_id": "bonus_points", "name": "Bonus", "score": 50,
        "max_score": 50, "reasoning": "", "feedback": "", "flags": [],
    })
    result = normalize_grade(payload, rubric)
    assert result["total_score"] == 89.0
    assert len(result["criteria_results"]) == 3
    assert "bonus_points" not in {c["criterion_id"]
                                  for c in result["criteria_results"]}


def test_normalize_canonicalises_flags(rubric):
    payload = grading_payload()
    payload["criteria_results"][0]["flags"] = ["No Outputs", "  RUNTIME_ERROR "]
    result = normalize_grade(payload, rubric)
    assert "no_outputs" in result["flags"]
    assert "runtime_error" in result["flags"]


def test_normalize_letter_grade_matches_percentage(rubric):
    for scores, expected in [
        ({"loading": 30, "model": 45, "writeup": 25}, "A+"),
        ({"loading": 25, "model": 38, "writeup": 20}, "B"),
        ({"loading": 10, "model": 15, "writeup": 5}, "F"),
    ]:
        result = normalize_grade(grading_payload(scores), rubric)
        assert result["letter_grade"] == expected, scores


# ---------------------------------------------------------------------
# grade_submission
# ---------------------------------------------------------------------
def test_grade_submission_happy_path(mock_claude, rubric, parsed):
    fake = mock_claude()
    result = grade_submission(
        parsed=parsed, rubric=rubric,
        assignment_name="HW3", assignment_description="Fit a model.",
    )

    assert result["total_score"] == 89.0
    assert result["letter_grade"] == "B+"
    assert result["summary_feedback"]
    assert result["ai_raw_output"] == grading_payload()
    assert result["usage"]["input_tokens"] == 1234

    # exactly one API call, with the right shape
    assert len(fake.calls) == 1
    call = fake.calls[0]
    # Whatever grading model is configured (opus, sonnet, ...) - not hard-coded,
    # so switching the model in .env does not break the test.
    from backend.config import settings
    assert call["model"] == settings.anthropic_grading_model
    assert call["thinking"]["type"] == "adaptive"
    assert call["output_config"]["format"]["type"] == "json_schema"
    # the system prompt is cached so a batch reuses the prefix
    assert call["system"][0]["cache_control"] == {"type": "ephemeral"}


def test_grade_submission_sends_the_rubric_verbatim(mock_claude, rubric, parsed):
    fake = mock_claude()
    grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")

    text = next(
        block["text"] for block in fake.calls[0]["messages"][0]["content"]
        if block["type"] == "text"
    )
    for criterion in rubric["criteria"]:
        assert criterion["id"] in text
        assert criterion["name"] in text


def test_grade_submission_attaches_images(mock_claude, rubric, parsed):
    fake = mock_claude()
    grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")

    content = fake.calls[0]["messages"][0]["content"]
    images = [b for b in content if b["type"] == "image"]
    assert len(images) == 1
    assert images[0]["source"]["media_type"] == "image/png"


def test_grade_submission_can_skip_images(mock_claude, rubric, parsed):
    fake = mock_claude()
    grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3",
                     include_images=False)
    content = fake.calls[0]["messages"][0]["content"]
    assert not [b for b in content if b["type"] == "image"]


def test_unrun_notebook_is_flagged_even_if_the_model_misses_it(mock_claude, rubric):
    """A deterministic check the model is not trusted to make."""
    mock_claude()
    unrun = parse_submission(SAMPLES / "unrun_submission.ipynb")
    result = grade_submission(parsed=unrun, rubric=rubric, assignment_name="HW3")
    assert "no_outputs" in result["flags"]


def test_runtime_error_is_flagged_from_the_parse(mock_claude, rubric):
    mock_claude()
    broken = parse_submission(SAMPLES / "error_submission.ipynb")
    result = grade_submission(parsed=broken, rubric=rubric, assignment_name="HW3")
    assert "runtime_error" in result["flags"]


def test_grade_submission_rejects_an_empty_rubric(parsed):
    with pytest.raises(GradingError, match="no criteria"):
        grade_submission(parsed=parsed, rubric={"criteria": []},
                         assignment_name="HW3")


def test_reference_solution_is_included_when_given(mock_claude, rubric, parsed):
    fake = mock_claude()
    solution = parse_submission(SAMPLES / "good_submission.py")
    grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3",
                     expected_solution=solution)
    text = next(b["text"] for b in fake.calls[0]["messages"][0]["content"]
                if b["type"] == "text")
    assert "Instructor reference solution" in text


# ---------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------
def test_missing_api_key_gives_a_useful_error(monkeypatch, rubric, parsed):
    from backend.config import settings
    reset_client()
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(GradingError, match="ANTHROPIC_API_KEY is not set"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")
    reset_client()


def test_placeholder_api_key_is_treated_as_missing(monkeypatch, rubric, parsed):
    from backend.config import settings
    reset_client()
    monkeypatch.setattr(settings, "anthropic_api_key", "your_anthropic_api_key_here")
    with pytest.raises(GradingError, match="ANTHROPIC_API_KEY is not set"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")
    reset_client()


def test_refusal_is_reported_clearly(mock_claude, rubric, parsed):
    fake = mock_claude()
    fake.stop_reason = "refusal"
    with pytest.raises(GradingError, match="declined to grade"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_truncated_response_is_reported_clearly(mock_claude, rubric, parsed):
    fake = mock_claude()
    fake.stop_reason = "max_tokens"
    with pytest.raises(GradingError, match="cut off"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_rate_limit_is_translated(mock_claude, rubric, parsed):
    fake = mock_claude()
    fake.raises = anthropic.RateLimitError(
        "429", response=_fake_httpx_response(429), body=None
    )
    with pytest.raises(GradingError, match="rate limit"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_auth_error_is_translated(mock_claude, rubric, parsed):
    fake = mock_claude()
    fake.raises = anthropic.AuthenticationError(
        "401", response=_fake_httpx_response(401), body=None
    )
    with pytest.raises(GradingError, match="rejected this API key"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_connection_error_is_translated(mock_claude, rubric, parsed):
    import httpx
    fake = mock_claude()
    fake.raises = anthropic.APIConnectionError(
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages")
    )
    with pytest.raises(GradingError, match="Could not reach"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_non_json_model_output_is_reported(mock_claude, rubric, parsed):
    mock_claude("I am not going to return JSON today.")
    with pytest.raises(GradingError, match="no JSON object"):
        grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def _fake_httpx_response(status_code: int):
    import httpx
    return httpx.Response(
        status_code,
        request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"),
    )


# ---------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------
def test_prompt_truncates_enormous_submissions(rubric):
    giant = {
        "file_type": "py", "images": [], "errors": [],
        "metadata": {}, "stats": {"n_code_cells": 1},
        "cells": [{"index": 0, "cell_type": "code", "source": "x = 1\n" * 200_000,
                   "outputs": [], "execution_count": 1, "has_error": False}],
    }
    prompt = prompts.build_grading_user_prompt(
        assignment_name="HW", assignment_description=None,
        rubric=rubric, parsed=giant, max_chars=5_000,
    )
    assert "characters omitted from the middle" in prompt
    # head and tail are both kept
    assert len(prompt) < 20_000


def test_prompt_marks_cells_with_no_output(rubric):
    unrun = parse_submission(SAMPLES / "unrun_submission.ipynb")
    prompt = prompts.build_grading_user_prompt(
        assignment_name="HW", assignment_description=None,
        rubric=rubric, parsed=unrun,
    )
    assert "Output: (none recorded)" in prompt
    assert "Notebook was executed: False" in prompt


def test_extract_rubric_from_text_uses_the_rubric_schema(mock_claude):
    fake = mock_claude({"title": "T", "total_points": 10,
                        "criteria": [], "grading_notes": ""})
    extract_rubric_from_text("Do the thing.", total_points=10)
    schema = fake.calls[0]["output_config"]["format"]["schema"]
    assert schema is prompts.RUBRIC_RESPONSE_SCHEMA
    assert fake.calls[0]["output_config"]["effort"] == "medium"


def test_extract_rubric_from_solution_reads_the_solution(mock_claude, parsed):
    """Builds a rubric from a parsed solution, using the rubric schema."""
    from backend.ai.grader import extract_rubric_from_solution

    fake = mock_claude({
        "title": "From solution", "total_points": 100,
        "criteria": [{"id": "c1", "name": "C1", "description": "d",
                      "max_points": 100, "keywords": [], "requires_output": False}],
        "grading_notes": "",
    })
    extract_rubric_from_solution(parsed, total_points=100)

    call = fake.calls[0]
    assert call["output_config"]["format"]["schema"] is prompts.RUBRIC_RESPONSE_SCHEMA
    assert call["output_config"]["effort"] == "medium"
    # The solution's system prompt tells the model output/code will vary.
    assert call["system"][0]["text"] == prompts.RUBRIC_FROM_SOLUTION_SYSTEM
    prompt = next(b["text"] for b in call["messages"][0]["content"] if b["type"] == "text")
    assert "worked solution" in prompt.lower()


def test_extract_rubric_from_solution_passes_through_the_professors_instructions(
        mock_claude, parsed):
    """
    Free text the professor types alongside the solution upload - the only
    way to tell the model something the file itself cannot show (marks per
    question, a section to grade leniently) - has to actually reach the
    model, and be marked as taking priority rather than just tacked on.
    """
    from backend.ai.grader import extract_rubric_from_solution

    fake = mock_claude({
        "title": "From solution", "total_points": 100,
        "criteria": [{"id": "c1", "name": "C1", "description": "d",
                      "max_points": 100, "keywords": [], "requires_output": False}],
        "grading_notes": "",
    })
    extract_rubric_from_solution(
        parsed, total_points=100,
        instructions="There are 20 questions, worth 5 points each. "
                    "Grade Question 12 leniently.")

    prompt = next(b["text"] for b in fake.calls[0]["messages"][0]["content"]
                 if b["type"] == "text")
    assert "Grade Question 12 leniently" in prompt
    assert "take priority" in prompt.lower()


def test_extract_rubric_from_solution_without_instructions_omits_the_section(
        mock_claude, parsed):
    """No stray "Additional instructions" heading when nothing was typed."""
    from backend.ai.grader import extract_rubric_from_solution

    fake = mock_claude({
        "title": "From solution", "total_points": 100,
        "criteria": [{"id": "c1", "name": "C1", "description": "d",
                      "max_points": 100, "keywords": [], "requires_output": False}],
        "grading_notes": "",
    })
    extract_rubric_from_solution(parsed, total_points=100, instructions="   ")

    prompt = next(b["text"] for b in fake.calls[0]["messages"][0]["content"]
                 if b["type"] == "text")
    assert "Additional instructions" not in prompt


# ---------------------------------------------------------------------
# A model that answers about criteria of its own invention
# ---------------------------------------------------------------------
def test_a_model_that_invents_its_own_criteria_is_called_out(rubric):
    """
    Small local models return a schema-valid response whose criterion ids
    are made up, so nothing matches the rubric and every criterion falls to
    zero. The clamping is right; handing a professor a silent 0/100 is not.
    """
    from backend.ai.grader import normalize_grade

    invented = {
        "criteria_results": [
            {"criterion_id": "1", "name": "Something else", "score": 2,
             "max_score": 2, "reasoning": "Looks fine.", "feedback": "Good."},
            {"criterion_id": "2", "name": "Another thing", "score": 2,
             "max_score": 2, "reasoning": "Fine too.", "feedback": "Good."},
        ],
        "summary_feedback": "Strong work overall.",
    }
    result = normalize_grade(invented, rubric)

    assert result["total_score"] == 0.0
    assert "rubric_ignored" in result["flags"]
    assert "criteria of its own" in result["summary_feedback"]
    assert "does not reflect" in result["summary_feedback"] or            "reflects the student" in result["summary_feedback"]


def test_a_partial_answer_is_not_treated_as_ignoring_the_rubric(rubric):
    """One matching criterion means the model understood the rubric."""
    from backend.ai.grader import normalize_grade

    first = rubric["criteria"][0]
    partial = {
        "criteria_results": [
            {"criterion_id": first["id"], "name": first["name"],
             "score": first["max_points"], "max_score": first["max_points"],
             "reasoning": "Correct.", "feedback": "Well done."},
            {"criterion_id": "invented", "name": "Made up", "score": 5,
             "max_score": 5, "reasoning": "", "feedback": ""},
        ],
        "summary_feedback": "Mostly good.",
    }
    result = normalize_grade(partial, rubric)

    assert "rubric_ignored" not in result["flags"]
    assert result["total_score"] == first["max_points"]
    assert result["summary_feedback"] == "Mostly good."


def test_the_prompt_names_every_criterion_id_outside_the_json(rubric, parsed):
    """
    Smaller local models read the rubric JSON and then answer about criteria
    they invented from the assignment's own headings. Restating the ids as
    an explicit closed set is what makes them comply.
    """
    from backend.ai import prompts

    prompt = prompts.build_grading_user_prompt(
        assignment_name="HW", assignment_description=None,
        rubric=rubric, parsed=parsed)

    listing = prompt.split("## The exact criteria to return", 1)
    assert len(listing) == 2, "the id list is missing from the prompt"
    tail = listing[1]
    for criterion in rubric["criteria"]:
        assert f"- {criterion['id']}" in tail
    assert str(len(rubric["criteria"])) in tail
