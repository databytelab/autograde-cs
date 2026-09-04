"""
Shared contract for every parser.

Each parser turns a student file into ONE dictionary shape so that
the rubric engine, the AI grader, and the similarity detector never
need to know which file format they came from.

    {
      "file_type":  "ipynb" | "html" | "py",
      "cells":      [ParsedCell, ...],
      "code":       "<all code concatenated, in order>",
      "markdown":   "<all prose concatenated, in order>",
      "images":     [ParsedImage, ...],
      "errors":     ["<traceback text>", ...],
      "stats":      {...},
      "metadata":   {...},
    }
"""
from __future__ import annotations

from typing import Any, TypedDict

# Only these extensions are accepted anywhere in the app.
SUPPORTED_EXTENSIONS = {".ipynb", ".html", ".htm", ".py"}

# Image payloads above this size are dropped rather than sent to the AI —
# a single 4K matplotlib figure can otherwise blow the request budget.
MAX_IMAGE_BYTES = 3_500_000


class ParsedCell(TypedDict):
    index: int
    cell_type: str          # "code" | "markdown" | "raw"
    source: str
    outputs: list[str]      # text/plain and stream output, already flattened
    execution_count: int | None
    has_error: bool
    # How many figures this cell actually rendered - PNG *and* SVG (graphviz,
    # plotly, ...). A cell whose code claims to plot but whose n_figures is 0
    # produced no figure, however confident its printed text sounds.
    n_figures: int


class ParsedImage(TypedDict):
    cell_index: int
    media_type: str         # e.g. "image/png"
    data_b64: str


class ParseError(Exception):
    """Raised when a file cannot be parsed at all (corrupt, wrong format)."""


def empty_result(file_type: str) -> dict[str, Any]:
    """A well-formed but empty parse result — every parser starts here."""
    return {
        "file_type": file_type,
        "cells": [],
        "code": "",
        "markdown": "",
        "images": [],
        "errors": [],
        "stats": {},
        "metadata": {},
    }


def finalize(result: dict[str, Any]) -> dict[str, Any]:
    """
    Derive `code`, `markdown` and `stats` from the cells the parser
    collected. Called at the end of every parser so the summary fields
    can never drift out of sync with the cell list.
    """
    code_parts, md_parts = [], []
    for cell in result["cells"]:
        if cell["cell_type"] == "code":
            code_parts.append(cell["source"])
        elif cell["cell_type"] == "markdown":
            md_parts.append(cell["source"])

    result["code"] = "\n\n".join(p for p in code_parts if p.strip())
    result["markdown"] = "\n\n".join(p for p in md_parts if p.strip())

    n_outputs = sum(len(c["outputs"]) for c in result["cells"])
    # Total figures counts SVG too; n_images counts only the base64 raster
    # images we can actually send to the vision model.
    n_figures = sum(c.get("n_figures", 0) for c in result["cells"])
    result["stats"] = {
        "n_cells": len(result["cells"]),
        "n_code_cells": sum(1 for c in result["cells"] if c["cell_type"] == "code"),
        "n_markdown_cells": sum(1 for c in result["cells"] if c["cell_type"] == "markdown"),
        "n_outputs": n_outputs,
        "n_images": len(result["images"]),
        "n_figures": max(n_figures, len(result["images"])),
        "n_errors": len(result["errors"]),
        # A notebook with code but zero outputs was almost certainly never run.
        "has_outputs": n_outputs > 0,
        "loc": sum(1 for line in result["code"].splitlines() if line.strip()),
        "chars": len(result["code"]) + len(result["markdown"]),
    }
    return result
