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


# ---------------------------------------------------------------------
# Third-party ".ipynb to HTML" converters - none of these are nbconvert,
# and each names its classes differently. Real student submissions in
# this shape used to come back completely empty: the cell wrapper matched
# structurally, so the classic-template parser claimed success, but its
# selectors were nbconvert-specific and found no source or output in any
# cell - a submission silently graded as blank.
# ---------------------------------------------------------------------
def test_html_runcell_style_export(tmp_path):
    """
    runcell.dev's export wraps each cell's execution-count label in a
    class containing "input-prompt" / "output-prompt" - which contain the
    substring "input", so a naive class match picks the *label* ("In
    [2]:") as the source instead of the code, and stripping the prompt
    text then leaves the cell looking empty.
    """
    from backend.parsers import parse_submission

    html = """<!DOCTYPE html><html><body>
    <div class="notebook-container">
      <div class="cell cell-code">
        <div class="cell-prompt input-prompt">In [2]:</div>
        <div class="cell-content">
          <div class="input-area"><pre>import numpy as np
print("Setup complete.")</pre></div>
          <div class="output-area">
            <div class="output-wrapper">
              <div class="cell-prompt output-prompt"></div>
              <div class="output-content">
                <div class="output-stream">Setup complete.
</div>
              </div>
            </div>
          </div>
        </div>
      </div>
      <div class="cell cell-markdown">
        <div class="cell-prompt prompt-empty">&nbsp;</div>
        <div class="cell-content">
          <div class="markdown-cell"><h2>Step 1</h2></div>
        </div>
      </div>
    </div>
    </body></html>"""
    f = tmp_path / "runcell.html"
    f.write_text(html, encoding="utf-8")

    result = parse_submission(str(f))
    assert result["metadata"]["template"] == "classic"
    code_cell = result["cells"][0]
    assert code_cell["cell_type"] == "code"
    assert "import numpy as np" in code_cell["source"]
    # The prompt label must not have been picked up as the source, and
    # must not survive inside it either.
    assert "In [2]:" not in code_cell["source"]
    assert code_cell["outputs"] == ["Setup complete."]
    assert result["cells"][1]["cell_type"] == "markdown"
    assert "Step 1" in result["cells"][1]["source"]


def test_html_bare_section_cells_with_execution_marker(tmp_path):
    """
    A converter that wraps each cell in a plain <section class="cell">,
    marks the execution count in its own <div>, and puts the output in a
    <div class="output"> right after the code <pre> - with no "input"-ish
    class anywhere, so the source has to be found by elimination (the
    first <pre> that is not itself inside the output block).
    """
    from backend.parsers import parse_submission

    html = """<html><body>
    <section class="cell"><h3>Step 0</h3><p>Setup.</p></section>
    <section class="cell">
      <div class="execution">In [1]</div>
      <pre><code>data = load()
print(data.shape)</code></pre>
      <div class="output"><pre>(20640, 9)
</pre></div>
    </section>
    </body></html>"""
    f = tmp_path / "section_cells.html"
    f.write_text(html, encoding="utf-8")

    result = parse_submission(str(f))
    assert result["metadata"]["template"] == "classic"
    cells = result["cells"]
    assert cells[0]["cell_type"] == "markdown"
    code_cell = cells[1]
    assert code_cell["cell_type"] == "code"
    assert "data = load()" in code_cell["source"]
    assert "(20640, 9)" not in code_cell["source"]      # output, not source
    assert code_cell["outputs"] == ["(20640, 9)"]


def test_html_pandoc_style_syntax_highlighting_is_not_mangled(tmp_path):
    """
    Quarto/Pandoc's notebook filter puts one <span> per syntax-highlighted
    token, e.g. `from` and `pathlib` are two separate spans on the same
    source line. Extracting a code block's text with a newline inserted
    between every text fragment - the right thing to do for a markdown
    cell built from block-level tags - tears code like this apart into
    one token per line instead of preserving the real line breaks that
    are already there in the raw HTML.
    """
    from backend.parsers import parse_submission

    html = """<html><body>
    <section class="cell markdown"><h2>Setup</h2></section>
    <div class="cell code" data-execution_count="1">
      <div class="sourceCode" id="cb1"><pre class="sourceCode python"><code class="sourceCode python"><span id="cb1-1"><a href="#cb1-1"></a><span class="im">from</span> pathlib <span class="im">import</span> Path</span>
<span id="cb1-2"><a href="#cb1-2"></a><span class="im">import</span> numpy <span class="im">as</span> np</span></code></pre></div>
      <div class="output stream stdout"><pre>Setup complete.
</pre></div>
    </div>
    </body></html>"""
    f = tmp_path / "pandoc.html"
    f.write_text(html, encoding="utf-8")

    result = parse_submission(str(f))
    code_cell = next(c for c in result["cells"] if c["cell_type"] == "code")
    assert code_cell["source"] == (
        "from pathlib import Path\nimport numpy as np"
    )
    assert code_cell["outputs"] == ["Setup complete."]


def test_html_no_cell_wrapper_falls_back_to_generic_but_still_pairs_outputs(tmp_path):
    """
    Some converters use no "cell" class at all - just bare <section>
    elements, an execution-count <div>, and a <pre class="output"> right
    after the code. With no wrapper to group by, the generic fallback has
    to reconstruct cell boundaries itself: each non-output <pre> starts a
    new cell, and any output-ish block between it and the next <pre>
    belongs to it.
    """
    from backend.parsers import parse_submission

    html = """<html><body>
    <section><div class="cell-label">In [1]</div>
      <pre><code>print("first")</code></pre><pre class="output">first
</pre>
    </section>
    <section><h3>A heading between cells</h3></section>
    <section><div class="cell-label">In [2]</div>
      <pre><code>print("second")</code></pre><pre class="output">second
</pre>
    </section>
    </body></html>"""
    f = tmp_path / "no_wrapper.html"
    f.write_text(html, encoding="utf-8")

    result = parse_submission(str(f))
    assert result["metadata"]["template"] == "generic"
    code_cells = [c for c in result["cells"] if c["cell_type"] == "code"]
    assert len(code_cells) == 2
    assert code_cells[0]["source"] == 'print("first")'
    assert code_cells[0]["outputs"] == ["first"]
    assert code_cells[1]["source"] == 'print("second")'
    assert code_cells[1]["outputs"] == ["second"]
    assert "A heading between cells" in result["markdown"]


def test_html_a_structurally_matched_but_empty_template_falls_through(tmp_path):
    """
    The core safety property: a template that finds cell-shaped elements
    but extracts nothing real from any of them must not be trusted just
    because it matched structurally - otherwise a converter this codebase
    has never seen parses "successfully" to a blank submission instead of
    falling through to a tier that can actually read it.
    """
    from backend.parsers import parse_submission

    # `.cell` divs exist (so _parse_classic matches structurally) but carry
    # no text of their own at all - only a decorative icon - so every cell
    # it builds is genuinely empty. The bare <pre> outside any `.cell`
    # wrapper is the only real content in the document, and only the
    # generic tier looks outside matched cells for it.
    html = """<html><body>
    <div class="cell widget-1"><img src="icon.png"></div>
    <div class="cell widget-2"><img src="icon.png"></div>
    <pre><code>print("real code, elsewhere in the page")</code></pre>
    </body></html>"""
    f = tmp_path / "empty_classic.html"
    f.write_text(html, encoding="utf-8")

    result = parse_submission(str(f))
    assert result["metadata"]["template"] == "generic"
    assert "real code, elsewhere in the page" in result["code"]
