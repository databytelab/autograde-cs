"""
Similarity detection between student submissions.

Two independent signals, combined:

**Token similarity** - the code is normalised (comments and docstrings
stripped, every identifier renamed to a placeholder, every literal
collapsed to a placeholder), broken into overlapping k-grams, and reduced
to a fingerprint set by winnowing. Two submissions are compared by the
Jaccard overlap of their fingerprints. This survives renaming variables,
reformatting, and reordering whitespace - the three things a student
does when copying.

**Structure similarity** - the AST is walked and reduced to a sequence of
node types only. Identical control flow with completely different names
still lines up here.

Neither signal is proof of anything. The output is a flag for a human to
review, which is why every flag carries the evidence that produced it.

Reference for the winnowing scheme:
Schleimer, Wilkerson & Aiken, "Winnowing: Local Algorithms for Document
Fingerprinting" (SIGMOD 2003).
"""
from __future__ import annotations

import ast
import hashlib
import io
import re
import tokenize
from dataclasses import dataclass, field
from typing import Any, Iterable

# k-gram length. 5 tokens is short enough to catch a copied helper
# function and long enough that common idioms do not match everything.
KGRAM_SIZE = 5
# Winnowing window. Guarantees any shared substring of length
# >= KGRAM_SIZE + WINDOW_SIZE - 1 tokens produces at least one shared
# fingerprint, while storing only ~2/(WINDOW_SIZE+1) of the hashes.
WINDOW_SIZE = 4

# Thresholds a professor sees as "severity".
HIGH_THRESHOLD = 0.85
MODERATE_THRESHOLD = 0.65
LOW_THRESHOLD = 0.50

# Below this many tokens a submission is too short to compare meaningfully -
# two 3-line answers to the same question are legitimately identical.
MIN_TOKENS = 40


@dataclass
class Fingerprint:
    """Everything we need to compare one submission against another."""
    submission_id: str
    token_hashes: set[int] = field(default_factory=set)
    ast_hashes: set[int] = field(default_factory=set)
    n_tokens: int = 0
    parse_failed: bool = False

    @property
    def comparable(self) -> bool:
        return self.n_tokens >= MIN_TOKENS


# ---------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------
# Python keywords must NOT be renamed - they carry the structure.
_KEYWORDS = frozenset(
    "False None True and as assert async await break class continue def del "
    "elif else except finally for from global if import in is lambda nonlocal "
    "not or pass raise return try while with yield match case".split()
)


def normalize_tokens(source: str) -> list[str]:
    """
    Reduce source to a rename-invariant token stream.

    Identifiers become "N", numbers "0", strings "S"; keywords and
    operators are kept verbatim. Comments, docstrings, whitespace and
    line structure are dropped entirely.
    """
    out: list[str] = []
    try:
        stream = tokenize.generate_tokens(io.StringIO(source).readline)
        prev_meaningful: str | None = None
        for tok in stream:
            kind, text = tok.type, tok.string

            if kind in (
                tokenize.COMMENT, tokenize.NL, tokenize.NEWLINE,
                tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING,
                tokenize.ENDMARKER,
            ):
                continue

            if kind == tokenize.STRING:
                # A string that stands alone as a statement is a docstring.
                if prev_meaningful in (None, ":", ";"):
                    continue
                out.append("S")
            elif kind == tokenize.NUMBER:
                out.append("0")
            elif kind == tokenize.NAME:
                out.append(text if text in _KEYWORDS else "N")
            elif kind == tokenize.OP:
                out.append(text)
            else:
                continue

            prev_meaningful = text
    except (tokenize.TokenError, IndentationError, SyntaxError):
        # Tokenising failed partway - keep whatever we collected and fall
        # back to a crude word split for the remainder.
        leftover = re.findall(r"[A-Za-z_]\w*|\d+|[^\s\w]", source)
        out.extend("N" if re.match(r"^[A-Za-z_]", t) else t for t in leftover)

    return out


def normalize_ast(source: str) -> tuple[list[str], bool]:
    """
    Reduce source to a sequence of AST node type names.

    Returns (sequence, parse_failed). On a syntax error the sequence is
    empty and parse_failed is True - the caller then relies on the token
    signal alone.
    """
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError):
        return [], True

    sequence: list[str] = []

    def walk(node: ast.AST) -> None:
        sequence.append(type(node).__name__)
        for child in ast.iter_child_nodes(node):
            walk(child)

    walk(tree)
    return sequence, False


# ---------------------------------------------------------------------
# Fingerprinting
# ---------------------------------------------------------------------
def _hash_kgram(kgram: Iterable[str]) -> int:
    """Stable 64-bit hash of a k-gram. blake2b keeps collisions negligible."""
    joined = "\x00".join(kgram).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(joined, digest_size=8).digest(), "big")


def winnow(tokens: list[str], k: int = KGRAM_SIZE, w: int = WINDOW_SIZE) -> set[int]:
    """
    Fingerprint a token sequence with the winnowing algorithm.

    In each sliding window of w consecutive k-gram hashes, keep the
    minimum. Ties keep the rightmost, which is what makes the selection
    position-independent: the same substring always yields the same
    fingerprints regardless of what surrounds it.
    """
    if len(tokens) < k:
        return set()

    hashes = [_hash_kgram(tokens[i : i + k]) for i in range(len(tokens) - k + 1)]
    if len(hashes) <= w:
        return {min(hashes)} if hashes else set()

    fingerprints: set[int] = set()
    for start in range(len(hashes) - w + 1):
        window = hashes[start : start + w]
        smallest = min(window)
        # Rightmost occurrence of the minimum
        offset = len(window) - 1 - window[::-1].index(smallest)
        fingerprints.add(hashes[start + offset])

    return fingerprints


def build_fingerprint(submission_id: str, parsed: dict[str, Any]) -> Fingerprint:
    """Build a Fingerprint from a parse result (see backend/parsers/base.py)."""
    code = parsed.get("code") or ""
    tokens = normalize_tokens(code)
    ast_sequence, parse_failed = normalize_ast(code)

    return Fingerprint(
        submission_id=submission_id,
        token_hashes=winnow(tokens),
        # AST sequences are dense and repetitive, so use a longer k-gram.
        ast_hashes=winnow(ast_sequence, k=KGRAM_SIZE + 3),
        n_tokens=len(tokens),
        parse_failed=parse_failed,
    )


# ---------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------
def jaccard(a: set[int], b: set[int]) -> float:
    """Overlap of two fingerprint sets, 0.0 to 1.0."""
    if not a or not b:
        return 0.0
    union = len(a | b)
    return len(a & b) / union if union else 0.0


def severity_for(score: float) -> str:
    """Map a similarity score onto the label a professor reviews."""
    if score >= HIGH_THRESHOLD:
        return "high"
    if score >= MODERATE_THRESHOLD:
        return "moderate"
    return "low"


def compare(a: Fingerprint, b: Fingerprint) -> dict[str, Any]:
    """
    Compare two fingerprints.

    Returns the score breakdown plus the method that produced the
    headline number, so a flag can always explain itself.
    """
    token_score = jaccard(a.token_hashes, b.token_hashes)
    ast_score = jaccard(a.ast_hashes, b.ast_hashes)

    if a.parse_failed or b.parse_failed:
        # No usable AST on one side - the token signal is all we have.
        combined, method = token_score, "token"
    else:
        # Token similarity is the stronger evidence (it survives renaming
        # but still reflects the actual code); structure corroborates it.
        combined = 0.65 * token_score + 0.35 * ast_score
        method = "combined"

    return {
        "similarity_score": round(combined, 3),
        "token_score": round(token_score, 3),
        "ast_score": round(ast_score, 3),
        "method": method,
        "severity": severity_for(combined),
        "comparable": a.comparable and b.comparable,
    }


def find_similar_pairs(
    fingerprints: list[Fingerprint],
    threshold: float = LOW_THRESHOLD,
) -> list[dict[str, Any]]:
    """
    Compare every pair and return those at or above `threshold`,
    highest score first.

    Pairs where either submission is too short to compare are skipped -
    flagging every three-line answer would bury the real signal.
    """
    results: list[dict[str, Any]] = []

    for i in range(len(fingerprints)):
        for j in range(i + 1, len(fingerprints)):
            a, b = fingerprints[i], fingerprints[j]
            if not (a.comparable and b.comparable):
                continue
            outcome = compare(a, b)
            if outcome["similarity_score"] >= threshold:
                results.append({
                    "submission_a_id": a.submission_id,
                    "submission_b_id": b.submission_id,
                    **outcome,
                })

    results.sort(key=lambda r: r["similarity_score"], reverse=True)
    return results
