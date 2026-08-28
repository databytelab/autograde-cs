"""File parsers for student submissions (.ipynb / .html / .py)."""
from backend.parsers.base import ParseError, SUPPORTED_EXTENSIONS
from backend.parsers.parser_router import detect_file_type, parse_submission

__all__ = [
    "ParseError",
    "SUPPORTED_EXTENSIONS",
    "detect_file_type",
    "parse_submission",
]
