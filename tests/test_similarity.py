"""Similarity detection tests - Stage 6.

Two properties matter more than the exact numbers:

  * a rename-only copy must score very high (that is the whole point)
  * unrelated solutions to the same problem must score low (or the
    professor drowns in false positives and stops reading the flags)
"""
from __future__ import annotations

import pytest

from backend.parsers import parse_submission
from backend.utils.similarity import (
    HIGH_THRESHOLD,
    MIN_TOKENS,
    Fingerprint,
    build_fingerprint,
    compare,
    find_similar_pairs,
    jaccard,
    normalize_ast,
    normalize_tokens,
    severity_for,
    winnow,
)
from tests.conftest import SAMPLES


def fingerprint_of(name: str, filename: str) -> Fingerprint:
    return build_fingerprint(name, parse_submission(SAMPLES / filename))


# ---------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------
def test_identifiers_are_renamed_but_keywords_are_kept():
    tokens = normalize_tokens("def total(items):\n    return sum(items)\n")
    assert "def" in tokens and "return" in tokens
    assert "total" not in tokens and "items" not in tokens
    assert tokens.count("N") >= 3


def test_renaming_variables_produces_identical_tokens():
    a = normalize_tokens("def f(x, y):\n    return x + y\n")
    b = normalize_tokens("def compute(alpha, beta):\n    return alpha + beta\n")
    assert a == b


def test_literals_are_collapsed():
    a = normalize_tokens("x = 42")
    b = normalize_tokens("x = 999999")
    assert a == b
    assert "0" in a


def test_comments_and_docstrings_are_dropped():
    with_noise = normalize_tokens(
        'def f():\n    """A docstring."""\n    # a comment\n    return 1\n'
    )
    without = normalize_tokens("def f():\n    return 1\n")
    assert with_noise == without


def test_string_literals_in_expressions_are_kept_as_placeholders():
    tokens = normalize_tokens('x = "hello"')
    assert "S" in tokens


def test_normalize_tokens_survives_broken_syntax():
    """A file that will not tokenise must still yield something."""
    tokens = normalize_tokens("def broken(:\n    return 1\n")
    assert tokens, "the fallback path should still produce tokens"


def test_normalize_ast_reports_parse_failure():
    sequence, failed = normalize_ast("def broken(:")
    assert failed is True
    assert sequence == []

    sequence, failed = normalize_ast("x = 1")
    assert failed is False
    assert "Module" in sequence


# ---------------------------------------------------------------------
# Winnowing
# ---------------------------------------------------------------------
def test_winnow_is_position_independent():
    """The same substring must fingerprint the same wherever it appears."""
    core = list("abcdefghijklmnop")
    a = winnow(["x", "y"] + core)
    b = winnow(core + ["z", "w"])
    assert a & b, "a shared substring must produce a shared fingerprint"


def test_winnow_is_deterministic():
    tokens = list("abcdefghijklmnop")
    assert winnow(tokens) == winnow(tokens)


def test_winnow_returns_empty_for_too_short_input():
    assert winnow(["a", "b"]) == set()


def test_jaccard_edges():
    assert jaccard(set(), set()) == 0.0
    assert jaccard({1, 2}, set()) == 0.0
    assert jaccard({1, 2, 3}, {1, 2, 3}) == 1.0
    assert jaccard({1, 2}, {3, 4}) == 0.0
    assert jaccard({1, 2}, {2, 3}) == pytest.approx(1 / 3)


# ---------------------------------------------------------------------
# The signal
# ---------------------------------------------------------------------
def test_a_file_is_identical_to_itself():
    a = fingerprint_of("a", "good_submission.py")
    b = fingerprint_of("b", "good_submission.py")
    result = compare(a, b)
    assert result["similarity_score"] == 1.0
    assert result["severity"] == "high"


def test_rename_only_copy_scores_high():
    """
    plagiarised.py is good_submission.py with every identifier renamed
    and the docstrings reworded. That must be caught.
    """
    original = fingerprint_of("original", "good_submission.py")
    copy = fingerprint_of("copy", "plagiarised.py")
    result = compare(original, copy)

    assert result["similarity_score"] >= HIGH_THRESHOLD
    assert result["severity"] == "high"
    assert result["method"] == "combined"


def test_genuinely_different_solutions_score_low():
    """
    different.py solves the same problem with gradient descent instead of
    the closed form. Flagging that would be a false accusation.
    """
    original = fingerprint_of("original", "good_submission.py")
    other = fingerprint_of("other", "different.py")
    result = compare(original, other)

    assert result["similarity_score"] < 0.3
    assert result["severity"] == "low"


def test_cross_format_comparison_works():
    """A .py and a .ipynb must be comparable - only the code matters."""
    py = fingerprint_of("py", "good_submission.py")
    nb = fingerprint_of("nb", "good_submission.ipynb")
    result = compare(py, nb)
    assert 0.0 <= result["similarity_score"] <= 1.0


def test_unparseable_file_falls_back_to_token_signal_only():
    broken = fingerprint_of("broken", "syntax_error.py")
    other = fingerprint_of("other", "different.py")
    assert broken.parse_failed is True
    result = compare(broken, other)
    assert result["method"] == "token"


# ---------------------------------------------------------------------
# Guards
# ---------------------------------------------------------------------
def test_short_submissions_are_not_comparable():
    tiny = Fingerprint("tiny", {1, 2}, {3}, n_tokens=MIN_TOKENS - 1)
    assert tiny.comparable is False


def test_find_similar_pairs_skips_short_submissions():
    """Two identical three-line answers are not evidence of anything."""
    a = Fingerprint("a", {1, 2, 3}, {4, 5}, n_tokens=5)
    b = Fingerprint("b", {1, 2, 3}, {4, 5}, n_tokens=5)
    assert find_similar_pairs([a, b]) == []


def test_find_similar_pairs_sorts_highest_first():
    fingerprints = [
        fingerprint_of("original", "good_submission.py"),
        fingerprint_of("copy", "plagiarised.py"),
        fingerprint_of("other", "different.py"),
        fingerprint_of("dup", "good_submission.py"),
    ]
    pairs = find_similar_pairs(fingerprints, threshold=0.5)

    assert pairs, "the copy must be flagged"
    scores = [p["similarity_score"] for p in pairs]
    assert scores == sorted(scores, reverse=True)
    # every flagged pair carries its evidence
    for pair in pairs:
        assert {"submission_a_id", "submission_b_id", "similarity_score",
                "token_score", "ast_score", "method", "severity"} <= set(pair)
    # the unrelated submission is never flagged
    flagged = {p["submission_a_id"] for p in pairs} | {
        p["submission_b_id"] for p in pairs}
    assert "other" not in flagged


def test_find_similar_pairs_respects_the_threshold():
    fingerprints = [
        fingerprint_of("original", "good_submission.py"),
        fingerprint_of("other", "different.py"),
    ]
    assert find_similar_pairs(fingerprints, threshold=0.9) == []
    assert find_similar_pairs(fingerprints, threshold=0.0)


def test_no_pair_is_reported_twice():
    fingerprints = [
        fingerprint_of("a", "good_submission.py"),
        fingerprint_of("b", "plagiarised.py"),
        fingerprint_of("c", "good_submission.py"),
    ]
    pairs = find_similar_pairs(fingerprints, threshold=0.5)
    keys = [frozenset((p["submission_a_id"], p["submission_b_id"]))
            for p in pairs]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("score,expected", [
    (1.0, "high"), (0.85, "high"), (0.84, "moderate"),
    (0.65, "moderate"), (0.64, "low"), (0.0, "low"),
])
def test_severity_bands(score, expected):
    assert severity_for(score) == expected
