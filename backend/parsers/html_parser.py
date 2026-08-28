"""
HTML parser — handles notebooks exported with `jupyter nbconvert --to html`
as well as plain HTML pages a student might submit.

nbconvert has used two different class conventions over the years:
  * JupyterLab template (current):  .jp-Cell / .jp-CodeCell / .jp-MarkdownCell
  * classic template (older):       .cell / .input_area / .output_area

We try each in turn and fall back to scraping <pre>/<code> blocks so that
an unrecognised export still yields something gradeable.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

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


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return _PROMPT.sub("", text).strip()


def _collect_images(scope, cell_index: int, images: list) -> None:
    """Pull base64 <img> payloads out of a cell's output area."""
    for img in scope.find_all("img"):
        match = _DATA_URI.match(img.get("src", "") or "")
        if not match:
            continue
        payload = match.group("data").replace("\n", "").strip()
        if len(payload) * 3 // 4 <= MAX_IMAGE_BYTES:
            images.append({
                "cell_index": cell_index,
                "media_type": match.group("mime").lower(),
                "data_b64": payload,
            })


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

        outputs, has_error = [], False
        for out in cell.select(".jp-OutputArea-output"):
            if "jp-RenderedText" in out.get("class", []) and out.select_one(".ansi-red-fg"):
                has_error = True
                result["errors"].append(out.get_text("\n").strip())
            text = _clean(out.get_text("\n"))
            if text:
                outputs.append(text)
            _collect_images(out, index, result["images"])

        result["cells"].append({
            "index": index, "cell_type": cell_type, "source": source,
            "outputs": outputs, "execution_count": None, "has_error": has_error,
        })
    return True


def _parse_classic(soup: BeautifulSoup, result: dict) -> bool:
    """Older nbconvert template. Returns True if it matched."""
    cells = soup.select("div.cell")
    if not cells:
        return False

    for index, cell in enumerate(cells):
        input_area = cell.select_one(".input_area")
        cell_type = "code" if input_area else "markdown"
        source_node = input_area or cell.select_one(".text_cell_render, .rendered_html")
        source = _clean(source_node.get_text("\n") if source_node else "")

        outputs, has_error = [], False
        for out in cell.select(".output_area, .output_subarea"):
            if out.select_one(".output_stderr") or "ename" in out.get_text():
                has_error = True
            text = _clean(out.get_text("\n"))
            if text:
                outputs.append(text)
            _collect_images(out, index, result["images"])

        result["cells"].append({
            "index": index, "cell_type": cell_type, "source": source,
            "outputs": outputs, "execution_count": None, "has_error": has_error,
        })
    return True


def _parse_generic(soup: BeautifulSoup, result: dict) -> None:
    """
    Last resort: treat every <pre>/<code> block as a code cell and the
    remaining body text as one markdown cell. Always succeeds.
    """
    index = 0
    for block in soup.find_all(["pre", "code"]):
        # Skip a <code> nested inside a <pre> we already captured
        if block.name == "code" and block.find_parent("pre"):
            continue
        source = _clean(block.get_text("\n"))
        if not source:
            continue
        result["cells"].append({
            "index": index, "cell_type": "code", "source": source,
            "outputs": [], "execution_count": None, "has_error": False,
        })
        index += 1

    body = soup.body or soup
    for tag in body.find_all(["pre", "code", "script", "style"]):
        tag.decompose()
    prose = _clean(body.get_text("\n"))
    if prose:
        prose = re.sub(r"\n{3,}", "\n\n", prose)
        result["cells"].append({
            "index": index, "cell_type": "markdown", "source": prose,
            "outputs": [], "execution_count": None, "has_error": False,
        })

    _collect_images(soup, 0, result["images"])


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

    result = empty_result("html")
    title = soup.find("title")
    result["metadata"] = {
        "title": title.get_text().strip() if title else None,
        "template": None,
    }

    if _parse_jupyterlab(soup, result):
        result["metadata"]["template"] = "jupyterlab"
    elif _parse_classic(soup, result):
        result["metadata"]["template"] = "classic"
    else:
        _parse_generic(soup, result)
        result["metadata"]["template"] = "generic"

    return finalize(result)
