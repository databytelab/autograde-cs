"""
The only entry point the rest of the app should use for parsing.

    from backend.parsers.parser_router import parse_submission
    parsed = parse_submission("uploads/abc/alice_hw3.ipynb")

Dispatches on file extension and guarantees the shared result shape
documented in base.py.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from backend.parsers import html_parser, notebook_parser, python_parser
from backend.parsers.base import SUPPORTED_EXTENSIONS, ParseError

_PARSERS: dict[str, Callable[[str | Path], dict[str, Any]]] = {
    ".ipynb": notebook_parser.parse,
    ".html": html_parser.parse,
    ".htm": html_parser.parse,
    ".py": python_parser.parse,
}


def detect_file_type(file_path: str | Path) -> str:
    """
    Return the canonical short type ("ipynb" / "html" / "py") for a path.
    Raises ParseError for anything we cannot grade.
    """
    suffix = Path(file_path).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ParseError(
            f"Unsupported file type '{suffix or '(none)'}'. "
            f"Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    return "html" if suffix in (".html", ".htm") else suffix.lstrip(".")


def parse_submission(file_path: str | Path) -> dict[str, Any]:
    """
    Parse any supported student submission.

    Raises ParseError if the extension is unsupported, the file is
    missing, or the content is too corrupt to read.
    """
    path = Path(file_path)
    if not path.exists():
        raise ParseError(f"File not found: {path}")
    if path.stat().st_size == 0:
        raise ParseError(f"{path.name} is empty (0 bytes)")

    detect_file_type(path)          # validates the extension
    parser = _PARSERS[path.suffix.lower()]
    result = parser(path)

    # Carry the source path through so downstream code can re-read the file
    result["metadata"]["source_path"] = str(path)
    result["metadata"]["original_filename"] = path.name
    return result
