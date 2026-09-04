"""Parser tests - Stage 3.

Every parser must return the shared shape from backend/parsers/base.py,
and must fail loudly rather than silently returning nothing.
"""
from __future__ import annotations

import pytest

from backend.parsers import ParseError, detect_file_type, parse_submission
from backend.parsers.python_parser import extract_structure
from tests.conftest import SAMPLES

REQUIRED_KEYS = {
    "file_type", "cells", "code", "markdown",
    "images", "errors", "stats", "metadata",
}


# ---------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------
@pytest.mark.parametrize("filename,expected", [
    ("hw.ipynb", "ipynb"),
    ("hw.html", "html"),
    ("hw.HTM", "html"),
    ("hw.py", "py"),
    ("HW.IPYNB", "ipynb"),
])
def test_detect_file_type(filename, expected):
    assert detect_file_type(filename) == expected


@pytest.mark.parametrize("filename", [
    "hw.txt", "hw.pdf", "hw.zip", "hw.docx", "hw", "hw.exe",
])
def test_detect_file_type_rejects_unsupported(filename):
    with pytest.raises(ParseError, match="Unsupported file type"):
        detect_file_type(filename)


def test_missing_file_raises():
    with pytest.raises(ParseError, match="File not found"):
        parse_submission(SAMPLES / "does_not_exist.ipynb")


def test_empty_file_raises():
    with pytest.raises(ParseError, match="empty"):
        parse_submission(SAMPLES / "empty.py")


def test_corrupt_notebook_raises():
    with pytest.raises(ParseError, match="not valid JSON"):
        parse_submission(SAMPLES / "corrupt.ipynb")


# ---------------------------------------------------------------------
# Shared contract
# ---------------------------------------------------------------------
@pytest.mark.parametrize("filename", [
    "good_submission.ipynb", "good_submission.html", "good_submission.py",
    "classic_submission.html", "generic.html", "different.py",
    "unrun_submission.ipynb", "error_submission.ipynb", "syntax_error.py",
])
def test_every_parser_returns_the_shared_shape(filename):
    result = parse_submission(SAMPLES / filename)

    assert REQUIRED_KEYS <= set(result), f"missing keys in {filename}"
    assert isinstance(result["cells"], list)
    assert isinstance(result["code"], str)
    assert isinstance(result["images"], list)
    assert isinstance(result["errors"], list)

    # stats must be derived from cells, never hand-set
    stats = result["stats"]
    assert stats["n_cells"] == len(result["cells"])
    assert stats["n_code_cells"] == sum(
        1 for c in result["cells"] if c["cell_type"] == "code"
    )
    assert stats["n_images"] == len(result["images"])

    # every cell carries the full cell contract
    for cell in result["cells"]:
        assert {"index", "cell_type", "source", "outputs",
                "execution_count", "has_error"} <= set(cell)

    # the router always records where it came from
    assert result["metadata"]["original_filename"] == filename


# ---------------------------------------------------------------------
# Notebooks
# ---------------------------------------------------------------------
def test_notebook_extracts_code_markdown_and_outputs():
    result = parse_submission(SAMPLES / "good_submission.ipynb")

    assert result["file_type"] == "ipynb"
    assert result["stats"]["n_code_cells"] == 4
    assert result["stats"]["n_markdown_cells"] == 4
    assert "import numpy as np" in result["code"]
    assert "Linear Regression" in result["markdown"]
    assert result["stats"]["has_outputs"] is True
    assert "(506, 14)" in " ".join(
        o for c in result["cells"] for o in c["outputs"]
    )


def test_notebook_extracts_images():
    result = parse_submission(SAMPLES / "good_submission.ipynb")
    assert len(result["images"]) == 1
    image = result["images"][0]
    assert image["media_type"] == "image/png"
    assert image["data_b64"]
    assert "\n" not in image["data_b64"]


def test_unrun_notebook_is_detected():
    """The single most common integrity signal: code with no outputs."""
    result = parse_submission(SAMPLES / "unrun_submission.ipynb")
    assert result["metadata"]["executed"] is False
    assert result["stats"]["has_outputs"] is False
    assert result["stats"]["n_outputs"] == 0


def test_executed_notebook_is_detected():
    result = parse_submission(SAMPLES / "good_submission.ipynb")
    assert result["metadata"]["executed"] is True


def test_notebook_error_outputs_are_captured():
    result = parse_submission(SAMPLES / "error_submission.ipynb")
    assert result["errors"], "the NameError traceback should be recorded"
    assert "NameError" in result["errors"][0]
    assert any(c["has_error"] for c in result["cells"])


# ---------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------
def test_html_jupyterlab_template():
    result = parse_submission(SAMPLES / "good_submission.html")
    assert result["metadata"]["template"] == "jupyterlab"
    assert result["stats"]["n_code_cells"] == 3
    assert "import numpy as np" in result["code"]
    assert "Eve Franklin" in result["markdown"]
    assert len(result["images"]) == 1


def test_html_classic_template():
    result = parse_submission(SAMPLES / "classic_submission.html")
    assert result["metadata"]["template"] == "classic"
    assert "import numpy as np" in result["code"]
    # The "In [1]:" prompt must be stripped, not graded as code
    assert "In [1]:" not in result["code"]


def test_html_generic_fallback():
    """An arbitrary HTML page must still yield something gradeable."""
    result = parse_submission(SAMPLES / "generic.html")
    assert result["metadata"]["template"] == "generic"
    assert "def fit" in result["code"]
    assert "Homework 3" in result["markdown"]


# ---------------------------------------------------------------------
# Python
# ---------------------------------------------------------------------
def test_python_extracts_ast_structure():
    result = parse_submission(SAMPLES / "good_submission.py")
    structure = result["metadata"]["structure"]

    assert structure["syntax_error"] is None
    assert "numpy" in structure["imports"]
    assert "sklearn.metrics.r2_score" in structure["imports"]

    names = {f["name"] for f in structure["functions"]}
    assert "fit" in names
    assert {"train", "predict", "__init__"} <= names | {
        m for c in structure["classes"] for m in c["methods"]
    }

    fit = next(f for f in structure["functions"] if f["name"] == "fit")
    assert fit["signature"] == "fit(X, y, *, ridge=0.0)"
    assert fit["docstring"]

    assert [c["name"] for c in structure["classes"]] == ["Model"]
    assert "main()" in structure["top_level_calls"]


def test_python_syntax_error_still_parses():
    """A broken file must be gradeable on what does parse."""
    result = parse_submission(SAMPLES / "syntax_error.py")
    assert result["errors"]
    assert "SyntaxError" in result["errors"][0]
    assert result["metadata"]["structure"]["syntax_error"] is not None
    # The source is still available for the grader to look at
    assert "def broken" in result["code"]


def test_python_module_docstring_becomes_markdown():
    result = parse_submission(SAMPLES / "good_submission.py")
    assert "Dan Ellis" in result["markdown"]


def test_extract_structure_handles_empty_source():
    structure = extract_structure("")
    assert structure["syntax_error"] is None
    assert structure["functions"] == []
    assert structure["imports"] == []


def test_extract_structure_signature_variants():
    source = (
        "def f(a, b=1, *args, c, d=2, **kwargs):\n    pass\n"
        "async def g(x):\n    pass\n"
    )
    structure = extract_structure(source)
    signatures = {f["name"]: f["signature"] for f in structure["functions"]}
    assert signatures["f"] == "f(a, b=1, *args, c, d=2, **kwargs)"
    assert signatures["g"] == "g(x)"


# ---------------------------------------------------------------------
# Student identity read from inside a submission
# ---------------------------------------------------------------------
def test_extract_identity_from_content_finds_name_and_id():
    from backend.utils.file_utils import extract_identity_from_parsed

    parsed = {"cells": [
        {"cell_type": "markdown",
         "source": "# Lab 2 - Decision Trees\nName: Jane Doe\nStudent ID: A1234567\n"},
        {"cell_type": "code", "source": "import pandas as pd"},
    ]}
    name, sid = extract_identity_from_parsed(parsed)
    assert name == "Jane Doe"
    assert sid == "A1234567"


def test_extract_identity_returns_none_when_absent():
    from backend.utils.file_utils import extract_identity_from_parsed

    parsed = {"cells": [{"cell_type": "code", "source": "x = 1  # no name here"}]}
    assert extract_identity_from_parsed(parsed) == (None, None)


def test_extract_identity_ignores_prose_mentions_of_name():
    from backend.utils.file_utils import extract_identity_from_parsed

    parsed = {"cells": [
        {"cell_type": "markdown",
         "source": "Choose a good name for your function and explain the method."},
    ]}
    # "name" appears but only as prose (no "Name: <value>" label).
    assert extract_identity_from_parsed(parsed)[0] is None


# ---------------------------------------------------------------------
# SVG / vector figures are counted (graphviz trees, plotly, ...)
# ---------------------------------------------------------------------
def test_html_counts_svg_figures(tmp_path):
    from backend.parsers import parse_submission

    html = """<html><body>
      <div class="jp-Cell jp-CodeCell">
        <div class="jp-InputArea-editor">import graphviz; draw_tree()</div>
        <div class="jp-OutputArea-output">Creating tree visualization... done</div>
        <div class="jp-OutputArea-output"><svg width="20" height="20"><g/></svg></div>
      </div>
    </body></html>"""
    f = tmp_path / "sol.html"
    f.write_text(html, encoding="utf-8")

    parsed = parse_submission(str(f))
    assert parsed["stats"]["n_figures"] >= 1        # the SVG is a figure
    assert parsed["cells"][0]["n_figures"] >= 1


def test_html_without_a_figure_reports_zero(tmp_path):
    from backend.parsers import parse_submission

    html = """<html><body>
      <div class="jp-Cell jp-CodeCell">
        <div class="jp-InputArea-editor">print("Tree visualization completed!")</div>
        <div class="jp-OutputArea-output">Tree visualization completed!</div>
      </div>
    </body></html>"""
    f = tmp_path / "sub.html"
    f.write_text(html, encoding="utf-8")

    parsed = parse_submission(str(f))
    assert parsed["stats"]["n_figures"] == 0
    assert parsed["cells"][0]["n_figures"] == 0
