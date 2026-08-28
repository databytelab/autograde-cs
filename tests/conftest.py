"""
Shared pytest fixtures.

Two things every test needs and must never share:

  * **A database of its own.** Each test gets a fresh SQLite file in a
    tmp directory, so tests can run in any order and a failure never
    leaves state behind for the next one.

  * **A fake Anthropic client.** No test may make a network call. The
    `mock_claude` fixture installs a stand-in that returns a scripted,
    schema-shaped response, so grading is fully exercised without an API
    key. Tests that want to prove the failure paths ask it for an error.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

SAMPLES = Path(__file__).parent / "sample_submissions"


# ---------------------------------------------------------------------
# Configuration - must happen before anything imports backend.config
# ---------------------------------------------------------------------
@pytest.fixture(autouse=True, scope="session")
def _test_settings(tmp_path_factory: pytest.TempPathFactory) -> None:
    """Point uploads at a tmp dir and pin a known secret key."""
    from backend.config import settings

    settings.upload_dir = str(tmp_path_factory.mktemp("uploads"))
    settings.secret_key = "test-secret-key-not-used-anywhere-real"
    settings.environment = "test"
    settings.anthropic_api_key = ""     # forces the mock path
    settings.canvas_base_url = ""
    settings.canvas_api_token = ""


# ---------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------
@pytest.fixture
def db_session(tmp_path: Path):
    """A clean database session backed by a throwaway SQLite file."""
    from backend.database import Base
    import backend.models  # noqa: F401 - registers every model on Base

    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    session = Session()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db_session, tmp_path: Path) -> TestClient:
    """A TestClient whose `get_db` dependency yields the test session."""
    from backend.database import get_db
    from backend.main import app

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------
# Authenticated users
# ---------------------------------------------------------------------
@pytest.fixture
def professor(client: TestClient) -> dict[str, Any]:
    """A registered professor plus their auth header."""
    response = client.post("/api/auth/register", json={
        "email": "prof@university.edu",
        "name": "Dr. Ada Lovelace",
        "password": "correct-horse-battery",
        "role": "professor",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "user": body["user"],
        "token": body["access_token"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


@pytest.fixture
def ta(client: TestClient) -> dict[str, Any]:
    """A registered TA - can grade, cannot finalize."""
    response = client.post("/api/auth/register", json={
        "email": "ta@university.edu",
        "name": "Sam Teaching-Assistant",
        "password": "another-good-password",
        "role": "ta",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    return {
        "user": body["user"],
        "token": body["access_token"],
        "headers": {"Authorization": f"Bearer {body['access_token']}"},
    }


@pytest.fixture
def course(client: TestClient, professor) -> dict[str, Any]:
    response = client.post(
        "/api/courses",
        json={"name": "CS 231N Computer Vision", "term": "Fall 2025"},
        headers=professor["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


SIMPLE_RUBRIC = {
    "title": "HW3 rubric",
    "criteria": [
        {"id": "loading", "name": "Data loading",
         "description": "Reads the CSV and reports its shape.",
         "max_points": 30, "requires_output": True},
        {"id": "model", "name": "Model fitting",
         "description": "Implements closed-form OLS correctly.",
         "max_points": 45},
        {"id": "writeup", "name": "Write-up",
         "description": "Explains the result in prose.",
         "max_points": 25},
    ],
    "grading_notes": "Strict on correctness, generous on style.",
}


@pytest.fixture
def assignment(client: TestClient, professor, course) -> dict[str, Any]:
    response = client.post(
        "/api/assignments",
        json={
            "course_id": course["id"],
            "name": "HW3 - Linear Regression",
            "description": "Fit a linear model to the housing data.",
            "total_possible_points": 100,
            "rubric_json": SIMPLE_RUBRIC,
        },
        headers=professor["headers"],
    )
    assert response.status_code == 201, response.text
    return response.json()


# ---------------------------------------------------------------------
# Mock Claude
# ---------------------------------------------------------------------
class FakeUsage:
    input_tokens = 1234
    output_tokens = 567
    cache_read_input_tokens = 0
    cache_creation_input_tokens = 1000


class FakeTextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class FakeResponse:
    def __init__(self, payload: Any, stop_reason: str = "end_turn") -> None:
        body = payload if isinstance(payload, str) else json.dumps(payload)
        self.content = [FakeTextBlock(body)]
        self.stop_reason = stop_reason
        self.stop_details = None
        self.usage = FakeUsage()
        self.model = "claude-opus-5"


class FakeMessages:
    """Records every call so tests can assert on what was sent."""

    def __init__(self, owner: "FakeAnthropic") -> None:
        self._owner = owner

    def create(self, **kwargs: Any) -> FakeResponse:
        self._owner.calls.append(kwargs)
        if self._owner.raises is not None:
            raise self._owner.raises
        responses = self._owner.responses
        payload = responses.pop(0) if len(responses) > 1 else responses[0]
        return FakeResponse(payload, stop_reason=self._owner.stop_reason)


class FakeAnthropic:
    def __init__(self, responses: list[Any]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.raises: Exception | None = None
        self.stop_reason = "end_turn"
        self.messages = FakeMessages(self)


def grading_payload(
    scores: dict[str, float] | None = None,
    flags: list[str] | None = None,
) -> dict[str, Any]:
    """A well-formed grading response for the SIMPLE_RUBRIC criteria."""
    scores = scores or {"loading": 27, "model": 40, "writeup": 22}
    return {
        "criteria_results": [
            {"criterion_id": "loading", "name": "Data loading",
             "score": scores.get("loading", 0), "max_score": 30,
             "reasoning": "The CSV is read and the shape printed.",
             "feedback": "You loaded the data correctly.", "flags": []},
            {"criterion_id": "model", "name": "Model fitting",
             "score": scores.get("model", 0), "max_score": 45,
             "reasoning": "pinv is used rather than inv, which is safer.",
             "feedback": "Good use of the pseudo-inverse.", "flags": []},
            {"criterion_id": "writeup", "name": "Write-up",
             "score": scores.get("writeup", 0), "max_score": 25,
             "reasoning": "A short but adequate conclusion.",
             "feedback": "Say more about why R-squared is 0.74.", "flags": []},
        ],
        "summary_feedback": "Solid work overall. Expand your conclusion next time.",
        "overall_flags": flags or [],
    }


@pytest.fixture
def mock_claude(monkeypatch):
    """
    Replace the Anthropic client with a scripted fake.

    Yields a factory:  `mock_claude(payload_or_list)` -> FakeAnthropic
    The returned object exposes `.calls` for assertions and `.raises` to
    force an error path.
    """
    from backend.ai import grader

    installed: list[FakeAnthropic] = []

    def install(responses: Any = None) -> FakeAnthropic:
        if responses is None:
            responses = [grading_payload()]
        elif not isinstance(responses, list):
            responses = [responses]

        fake = FakeAnthropic(responses)
        monkeypatch.setattr(grader, "_client", fake)
        monkeypatch.setattr(grader, "get_client", lambda: fake)
        installed.append(fake)
        return fake

    yield install

    grader.reset_client()


# ---------------------------------------------------------------------
# Sample files
# ---------------------------------------------------------------------
@pytest.fixture
def sample(request) -> Path:
    """Indirect fixture: `@pytest.mark.parametrize('sample', [...], indirect=True)`."""
    path = SAMPLES / request.param
    assert path.exists(), f"missing fixture file: {path}"
    return path


def upload_sample(client: TestClient, assignment_id: str, headers: dict,
                  *filenames: str):
    """Helper: POST one or more sample files as submissions."""
    files = [
        ("files", (name, (SAMPLES / name).read_bytes(), "application/octet-stream"))
        for name in filenames
    ]
    return client.post(
        f"/api/assignments/{assignment_id}/submissions",
        files=files, headers=headers,
    )
