"""
HTML parser — handles notebooks exported with `jupyter nbconvert --to html`,
notebooks exported by any of the various third-party "convert my .ipynb to
HTML" tools students find on the web, and plain HTML pages a student might
submit instead.

Real submissions have shown at least half a dozen distinct export dialects
beyond nbconvert's own two templates — each from a different converter,
each using its own class names for the same underlying idea (a cell has an
input area and zero or more output areas). Matching exact class strings
tool-by-tool is a losing game: the day a student finds a new converter, its
submission silently parses to nothing, and nothing about that is visible
in the UI — the grade just comes back low, or zero, for a reason no one can
see.

So this module works in tiers, each one strictly more permissive than the
last, and — critically — a tier is only trusted if it actually finds real
content. A tier that matches structurally (it can see "cells") but extracts
nothing from any of them is treated as a wrong guess, not a successful
parse, and control falls through to the next tier:

  1. `_parse_jupyterlab` — the current nbconvert template
     (`.jp-Cell` / `.jp-CodeCell` / `.jp-MarkdownCell`), matched by exact
     class name because it is extremely stable and by far the most common
     export in practice (Jupyter's and Colab's own "Download as HTML").

  2. `_parse_classic` — anything that wraps each cell in an element whose
     class contains the token "cell" (nbconvert's older template, and
     every third-party converter we have seen). Within a cell, source and
     output are found by *signal* rather than by one tool's exact naming:
     a class containing "input"/"source"/"code" (and not "output") marks
     the source area; a class containing "output" marks an output block,
     however it is nested. This one heuristic — "the word output is
     somewhere in the class" — has matched every converter seen so far
     without listing any of them by name.

  3. `_parse_generic` — no cell wrapper at all. Every <pre> becomes a code
     cell (skipping ones that sit inside something output-ish), anything
     output-ish between one <pre> and the next is attached to the cell
     before it, and everything else becomes prose. Always succeeds, so a
     submission never comes back as nothing gradeable.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup, Tag

from backend.parsers.base import (
    MAX_IMAGE_BYTES,
    ParseError,
    empty_result,
    finalize,
)

# src="data:image/png;base64,iVBOR..."
_DATA_URI = re.compile(r"^data:(?P<mime>image/[a-z+]+);base64,(?P<data>.+)$", re.I | re.S)

# nbconvert prefixes every input line with the prompt "In [12]:"
_PROMPT = re.compile(r"^\s*(In|Out)\s*\[[\d\s]*\]:\s*", re.M)

# The one signal every converter we have seen agrees on: an output block's
# class mentions "output" somewhere, however else it names things.
_OUTPUTISH = re.compile(r"output", re.I)
_CODEISH = re.compile(r"input|source|code", re.I)
_ERRORISH = re.compile(r"error|stderr", re.I)
# A prompt/label element (e.g. runcell.dev's `.input-prompt`, which holds
# only the text "In [2]:") is not the source or the output itself - it just
# sits beside one. "input-prompt" contains the substring "input", so
# without this exclusion `_CODEISH` picks the label instead of the actual
# code, and the label's own text - "In [2]:" - is then stripped to nothing
# by `_PROMPT`, leaving the cell looking like it has no source at all.
_PROMPTISH = re.compile(r"prompt", re.I)
# Tokens that mean "markdown" but do not contain the substring - checked
# as whole tokens, not substrings, so this stays a short, safe list.
_MARKDOWN_TOKENS = {"md-cell", "md_cell", "text_cell", "text-cell", "prose"}


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _PROMPT.sub("", text).strip()


def _get_text(node: Tag, *, block_join: bool) -> str:
    """
    Flatten a node's text.

    `block_join=True` inserts a newline between text fragments, for prose
    where sibling block elements (a heading followed by a paragraph) have
    no literal newline between them in the source HTML. `block_join=False`
    takes the text exactly as written, for <pre> blocks — which already
    contain real newlines, and where inserting more would tear a
    syntax-highlighted line (one <span> per token) apart into one token
    per line.
    """
    return _clean(node.get_text("\n" if block_join else ""))


def _class_tokens(el: Tag) -> list[str]:
    return [t.lower() for t in (el.get("class") or [])]


def _has_token_matching(el: Tag, pattern: re.Pattern) -> bool:
    return any(pattern.search(t) for t in _class_tokens(el))


def _within_outputish(el: Tag, boundary: Tag) -> bool:
    """True if `el` or any ancestor up to (not including) `boundary` is
    marked as an output block - used to keep output text out of a cell's
    extracted *source*, regardless of how deeply it is nested."""
    node: Tag | None = el
    while node is not None and node is not boundary:
        if _has_token_matching(node, _OUTPUTISH):
            return True
        node = node.parent
    return False


def _top_level(nodes: list[Tag]) -> list[Tag]:
    """Drop any node that is a descendant of another node in the list, so
    a wrapper and its own inner wrapper are never both counted."""
    ids = {id(n) for n in nodes}
    kept = []
    for n in nodes:
        if any(id(p) in ids for p in n.parents):
            continue
        kept.append(n)
    return kept


def _is_errorish(node: Tag) -> bool:
    if _has_token_matching(node, _ERRORISH):
        return True
    return any(_has_token_matching(el, _ERRORISH) for el in node.find_all(True))


def _collect_figures(scope: Tag, cell_index: int, images: list) -> int:
    """
    Pull base64 <img> payloads out of a cell's output area and count every
    figure it rendered - raster (PNG/JPEG) *and* vector (<svg>, e.g. a
    graphviz decision tree or a plotly chart).

    Returns the number of figures found. The SVG ones cannot be sent to the
    vision model, but their presence (or absence) is what lets the grader tell
    that a plot a student claimed to draw is actually missing.
    """
    n_figures = 0
    for img in scope.find_all("img"):
        match = _DATA_URI.match(img.get("src", "") or "")
        if not match:
            continue
        n_figures += 1
        payload = match.group("data").replace("\n", "").strip()
        if len(payload) * 3 // 4 <= MAX_IMAGE_BYTES:
            images.append({
                "cell_index": cell_index,
                "media_type": match.group("mime").lower(),
                "data_b64": payload,
            })
    n_figures += len(scope.find_all("svg"))
    return n_figures


def _parse_jupyterlab(soup: BeautifulSoup, result: dict) -> bool:
    """Current nbconvert template. Returns True if it matched."""
    cells = soup.select("div.jp-Cell")
    if not cells:
        return False

    for index, cell in enumerate(cells):
        classes = cell.get("class", [])
        is_code = "jp-CodeCell" in classes
        cell_type = "code" if is_code else "markdown"

        source_node = cell.select_one(".jp-InputArea-editor, .jp-RenderedMarkdown")
        source = _clean(source_node.get_text("\n") if source_node else "")

        outputs, has_error, n_figures = [], False, 0
        for out in cell.select(".jp-OutputArea-output"):
            if "jp-RenderedText" in out.get("class", []) and out.select_one(".ansi-red-fg"):
                has_error = True
                result["errors"].append(out.get_text("\n").strip())
            text = _clean(out.get_text("\n"))
            if text:
                outputs.append(text)
            n_figures += _collect_figures(out, index, result["images"])

        result["cells"].append({
            "index": index, "cell_type": cell_type, "source": source,
            "outputs": outputs, "execution_count": None, "has_error": has_error,
            "n_figures": n_figures,
        })
    return True


# ---------------------------------------------------------------------
# Cell-wrapper based: anything with a class token containing "cell"
# ---------------------------------------------------------------------
def _code_wrapper(cell: Tag) -> Tag | None:
    """The first descendant that looks like a source-code container,
    skipping anything inside an output-ish block or that is itself just a
    prompt label (e.g. "In [2]:") rather than the code itself."""
    for el in cell.find_all(True):
        if _within_outputish(el, cell) or _has_token_matching(el, _PROMPTISH):
            continue
        if _has_token_matching(el, _CODEISH):
            return el
    return None


def _cell_type(cell: Tag) -> str:
    tokens = _class_tokens(cell)
    if any("markdown" in t for t in tokens) or any(t in _MARKDOWN_TOKENS for t in tokens):
        return "markdown"
    if any("code" in t for t in tokens if "output" not in t):
        return "code"
    if _code_wrapper(cell) is not None:
        return "code"
    if cell.select_one(".text_cell_render, .rendered_html, .markdown-cell, .md-content"):
        return "markdown"
    return "code" if cell.find("pre") else "markdown"


def _code_source(cell: Tag) -> str:
    wrapper = _code_wrapper(cell)
    if wrapper is not None:
        return _get_text(wrapper, block_join=False)
    # No wrapper carries a recognisable class (bare <pre><code>...</code></pre>
    # with no styling hooks at all) - take the first <pre> that is not
    # itself sitting inside an output block.
    for pre in cell.find_all("pre"):
        if not _within_outputish(pre, cell):
            return _get_text(pre, block_join=False)
    return ""


def _markdown_source(cell: Tag) -> str:
    wrapper = cell.select_one(".text_cell_render, .rendered_html, .markdown-cell, .md-content")
    if wrapper is not None:
        return _get_text(wrapper, block_join=True)
    # A markdown cell never legitimately contains a <pre> (a cell with one
    # is classified "code" by `_cell_type` before we get here), so the
    # whole cell's text is safe to take as-is.
    return _get_text(cell, block_join=True)


def _extract_outputs(cell: Tag, index: int, result: dict) -> tuple[list[str], bool, int]:
    candidates = [el for el in cell.find_all(True)
                  if _has_token_matching(el, _OUTPUTISH)
                  and not _has_token_matching(el, _PROMPTISH)]
    outputs, has_error = [], False
    for node in _top_level(candidates):
        text = _get_text(node, block_join=True)
        if text:
            outputs.append(text)
        if _is_errorish(node):
            has_error = True
            if text:
                result["errors"].append(text)
    n_figures = _collect_figures(cell, index, result["images"])
    return outputs, has_error, n_figures


def _parse_classic(soup: BeautifulSoup, result: dict) -> bool:
    """
    Any cell-wrapper export: nbconvert's older template, and every
    third-party ".ipynb to HTML" converter seen in practice, no matter
    what its sub-class names look like. Returns True if it matched.
    """
    cells = _top_level(soup.select(".cell"))
    if not cells:
        return False

    for index, cell in enumerate(cells):
        cell_type = _cell_type(cell)
        source = _code_source(cell) if cell_type == "code" else _markdown_source(cell)
        outputs, has_error, n_figures = _extract_outputs(cell, index, result)

        result["cells"].append({
            "index": index, "cell_type": cell_type, "source": source,
            "outputs": outputs, "execution_count": None, "has_error": has_error,
            "n_figures": n_figures,
        })
    return True


# ---------------------------------------------------------------------
# Last resort: no cell wrapper anywhere
# ---------------------------------------------------------------------
def _parse_generic(soup: BeautifulSoup, result: dict) -> None:
    """
    No recognisable cell wrapper anywhere in the document. Every <pre> that
    is not itself output-ish becomes a code cell; any output-ish block
    that falls between one such <pre> and the next is attached to the cell
    before it, using the same "output" class signal `_parse_classic` uses -
    so a converter we have never seen still works, as long as its output
    wrapper's class mentions "output" somewhere. Everything else becomes
    one prose cell. Always succeeds.
    """
    body = soup.body or soup
    for tag in body.find_all(["script", "style"]):
        tag.decompose()

    flat = body.find_all(True)
    position = {id(el): i for i, el in enumerate(flat)}

    code_cells: list[dict[str, Any]] = []
    for pre in body.find_all("pre"):
        if _within_outputish(pre, body) or pre.find_parent("pre"):
            continue
        source = _get_text(pre, block_join=False)
        if not source:
            continue
        code_cells.append({
            "pos": position.get(id(pre), 0), "source": source,
            "outputs": [], "has_error": False,
        })

    output_candidates = _top_level(
        [el for el in flat if _has_token_matching(el, _OUTPUTISH)
         and not _has_token_matching(el, _PROMPTISH)]
    )
    for node in output_candidates:
        pos = position.get(id(node), 0)
        target = None
        for cc in code_cells:
            if cc["pos"] <= pos:
                target = cc
            else:
                break
        if target is None:
            continue
        text = _get_text(node, block_join=True)
        if text:
            target["outputs"].append(text)
        if _is_errorish(node):
            target["has_error"] = True
            if text:
                result["errors"].append(text)

    for index, cc in enumerate(code_cells):
        result["cells"].append({
            "index": index, "cell_type": "code", "source": cc["source"],
            "outputs": cc["outputs"], "execution_count": None,
            "has_error": cc["has_error"], "n_figures": 0,
        })

    # Prose: everything left once every <pre> and every output-ish block is
    # removed. Worked out on a fresh copy - the original tree is still
    # needed below for figure collection.
    scratch = BeautifulSoup(str(body), "lxml")
    for tag in scratch.find_all("pre"):
        tag.decompose()
    for tag in [el for el in scratch.find_all(True) if _has_token_matching(el, _OUTPUTISH)]:
        tag.decompose()
    prose = _get_text(scratch, block_join=True)
    if prose:
        result["cells"].append({
            "index": len(code_cells), "cell_type": "markdown", "source": prose,
            "outputs": [], "execution_count": None, "has_error": False,
            "n_figures": 0,
        })

    # Figures: with no cell structure to place them precisely, attach all
    # of them to the last code cell rather than guessing at index 0 - the
    # last cell is the one most likely to be near a plot in a report that
    # builds up to a result.
    if code_cells:
        target_index = len(code_cells) - 1
        n_figures = _collect_figures(body, target_index, result["images"])
        result["cells"][target_index]["n_figures"] += n_figures
    else:
        _collect_figures(body, 0, result["images"])


def _has_real_content(result: dict) -> bool:
    """
    Whether a tier actually extracted anything, as opposed to matching
    cell-shaped elements but finding every one of them empty - which is
    exactly what happens when a template's selectors are close to a
    converter's markup but not quite right, and is worse than finding no
    match at all: it looks like a successful parse of a blank submission.
    """
    return any(c["source"].strip() or c["outputs"] for c in result["cells"])


def parse(file_path: str | Path) -> dict[str, Any]:
    """Parse an .html/.htm file into the shared parse-result shape."""
    path = Path(file_path)
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParseError(f"Could not read {path.name}: {exc}") from exc

    if not raw.strip():
        raise ParseError(f"{path.name} is empty")

    # lxml is fast and tolerant of the malformed markup exports often produce
    soup = BeautifulSoup(raw, "lxml")

    title = soup.find("title")
    base_metadata = {
        "title": title.get_text().strip() if title else None,
        "template": None,
    }

    for parser_fn, name in ((_parse_jupyterlab, "jupyterlab"), (_parse_classic, "classic")):
        candidate = empty_result("html")
        candidate["metadata"] = dict(base_metadata)
        if parser_fn(soup, candidate) and _has_real_content(candidate):
            candidate["metadata"]["template"] = name
            return finalize(candidate)

    candidate = empty_result("html")
    candidate["metadata"] = dict(base_metadata)
    _parse_generic(soup, candidate)
    candidate["metadata"]["template"] = "generic"
    return finalize(candidate)
