"""Provider layer tests — the OpenAI / local / Anthropic switch.

These prove the new multi-provider grading path: the factory picks the right
backend from settings, the OpenAI-compatible provider builds a correct
Chat Completions request (schema, images, models), parses the reply, maps
usage, and translates every error to GradingError. No network access —
`openai_provider.make_client` is replaced with a scripted fake.
"""
from __future__ import annotations

import json

import httpx2
import openai
import pytest

from backend.ai import grader
from backend.ai.providers import get_provider, reset_provider
from backend.ai.providers.openai_provider import OpenAICompatibleProvider
from backend.config import settings
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
# A scripted fake OpenAI client
# ---------------------------------------------------------------------
class _Msg:
    def __init__(self, content: str) -> None:
        self.content = content


class _Choice:
    def __init__(self, content: str, finish: str = "stop") -> None:
        self.message = _Msg(content)
        self.finish_reason = finish


class _Usage:
    prompt_tokens = 100
    completion_tokens = 50
    prompt_tokens_details = None


class _CCResponse:
    def __init__(self, payload, finish: str = "stop") -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        self.choices = [_Choice(body, finish)]
        self.usage = _Usage()
        self.model = "gpt-4o"


class _Completions:
    def __init__(self, owner: "FakeOpenAI") -> None:
        self._owner = owner

    def create(self, **kwargs):
        self._owner.calls.append(kwargs)
        # Simulate a server that rejects strict json_schema the first time.
        if (self._owner.reject_schema_once
                and kwargs.get("response_format", {}).get("type") == "json_schema"):
            self._owner.reject_schema_once = False
            raise openai.BadRequestError(
                "response_format json_schema not supported",
                response=httpx2.Response(400, request=_req()),
                body=None,
            )
        if self._owner.raises is not None:
            raise self._owner.raises
        responses = self._owner.responses
        payload = responses.pop(0) if len(responses) > 1 else responses[0]
        return _CCResponse(payload, finish=self._owner.finish_reason)


class _Chat:
    def __init__(self, owner: "FakeOpenAI") -> None:
        self.completions = _Completions(owner)


class FakeOpenAI:
    def __init__(self, responses) -> None:
        self.responses = responses
        self.calls: list[dict] = []
        self.raises: Exception | None = None
        self.finish_reason = "stop"
        self.reject_schema_once = False
        self.chat = _Chat(self)


def _req():
    return httpx2.Request("POST", "https://api.openai.com/v1/chat/completions")


@pytest.fixture
def mock_openai(monkeypatch):
    """
    Switch the active provider to OpenAI and install a scripted fake client.

    Yields a factory: `mock_openai(payload_or_list)` -> FakeOpenAI, exposing
    `.calls`, `.raises`, `.finish_reason`, and `.reject_schema_once`.
    """
    from backend.ai.providers import openai_provider

    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "sk-test-key")
    reset_provider()

    installed: list[FakeOpenAI] = []

    def install(responses=None) -> FakeOpenAI:
        if responses is None:
            responses = [grading_payload()]
        elif not isinstance(responses, list):
            responses = [responses]
        fake = FakeOpenAI(responses)
        monkeypatch.setattr(openai_provider, "make_client", lambda *a, **k: fake)
        reset_provider()
        installed.append(fake)
        return fake

    yield install
    reset_provider()


# ---------------------------------------------------------------------
# Factory selection
# ---------------------------------------------------------------------
def test_factory_defaults_to_openai(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    reset_provider()
    provider = get_provider()
    assert provider.name == "openai"
    assert isinstance(provider, OpenAICompatibleProvider)
    reset_provider()


def test_factory_selects_local(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "local")
    reset_provider()
    provider = get_provider()
    assert provider.name == "local"
    assert provider._grading_model == settings.local_model
    assert provider._base_url == settings.local_base_url
    reset_provider()


def test_factory_selects_anthropic(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    reset_provider()
    provider = get_provider()
    assert provider.name == "anthropic"
    reset_provider()


def test_unknown_provider_falls_back_to_openai(monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "banana")
    reset_provider()
    assert get_provider().name == "openai"
    reset_provider()


# ---------------------------------------------------------------------
# OpenAI grading path
# ---------------------------------------------------------------------
def test_openai_grades_and_totals_in_python(mock_openai, rubric, parsed):
    fake = mock_openai()
    result = grader.grade_submission(
        parsed=parsed, rubric=rubric, assignment_name="HW3",
    )
    assert result["total_score"] == 89.0
    assert result["letter_grade"] == "B+"
    assert result["ai_raw_output"] == grading_payload()

    call = fake.calls[0]
    assert call["model"] == "gpt-4o"
    assert call["response_format"]["type"] == "json_schema"
    assert call["response_format"]["json_schema"]["strict"] is True
    roles = [m["role"] for m in call["messages"]]
    assert roles == ["system", "user"]


def test_openai_maps_usage(mock_openai, rubric, parsed):
    mock_openai()
    result = grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")
    assert result["usage"]["input_tokens"] == 100
    assert result["usage"]["output_tokens"] == 50


def test_openai_attaches_images_as_data_uris(mock_openai, rubric, parsed):
    fake = mock_openai()
    grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")
    user_content = fake.calls[0]["messages"][1]["content"]
    image_parts = [p for p in user_content if p.get("type") == "image_url"]
    assert image_parts, "expected at least one figure attached"
    assert image_parts[0]["image_url"]["url"].startswith("data:image/png;base64,")


def test_openai_can_skip_images(mock_openai, rubric, parsed):
    fake = mock_openai()
    grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3",
                            include_images=False)
    # No images → the user turn is a plain string, not a content list.
    assert isinstance(fake.calls[0]["messages"][1]["content"], str)


def test_openai_falls_back_when_json_schema_unsupported(mock_openai, rubric, parsed):
    """A local server that rejects strict schemas still grades."""
    fake = mock_openai()
    fake.reject_schema_once = True
    result = grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")
    assert result["total_score"] == 89.0
    # Two calls: json_schema (rejected) then json_object.
    assert fake.calls[1]["response_format"]["type"] == "json_object"


def test_openai_truncated_response_is_reported(mock_openai, rubric, parsed):
    fake = mock_openai()
    fake.finish_reason = "length"
    with pytest.raises(grader.GradingError, match="cut off"):
        grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_openai_auth_error_is_translated(mock_openai, rubric, parsed):
    fake = mock_openai()
    fake.raises = openai.AuthenticationError(
        "invalid key", response=httpx2.Response(401, request=_req()), body=None
    )
    with pytest.raises(grader.GradingError, match="rejected the API key"):
        grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_openai_rate_limit_is_translated(mock_openai, rubric, parsed):
    fake = mock_openai()
    fake.raises = openai.RateLimitError(
        "429", response=httpx2.Response(429, request=_req()), body=None
    )
    with pytest.raises(grader.GradingError, match="rate limit"):
        grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_openai_connection_error_is_translated(mock_openai, rubric, parsed):
    fake = mock_openai()
    fake.raises = openai.APIConnectionError(request=_req())
    with pytest.raises(grader.GradingError, match="Could not reach"):
        grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")


def test_missing_openai_key_gives_useful_error(monkeypatch, rubric, parsed):
    monkeypatch.setattr(settings, "llm_provider", "openai")
    monkeypatch.setattr(settings, "openai_api_key", "")
    reset_provider()
    with pytest.raises(grader.GradingError, match="OPENAI_API_KEY is not set"):
        grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")
    reset_provider()


# ---------------------------------------------------------------------
# Local provider
# ---------------------------------------------------------------------
def test_local_provider_uses_its_model_and_needs_no_key(monkeypatch, rubric, parsed):
    from backend.ai.providers import openai_provider

    monkeypatch.setattr(settings, "llm_provider", "local")
    monkeypatch.setattr(settings, "local_model", "qwen2.5-coder:7b")
    reset_provider()
    fake = FakeOpenAI([grading_payload()])
    monkeypatch.setattr(openai_provider, "make_client", lambda *a, **k: fake)
    reset_provider()

    result = grader.grade_submission(parsed=parsed, rubric=rubric, assignment_name="HW3")
    assert result["total_score"] == 89.0
    assert fake.calls[0]["model"] == "qwen2.5-coder:7b"
    reset_provider()
