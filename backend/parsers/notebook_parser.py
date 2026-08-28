"""
Jupyter notebook (.ipynb) parser.

Reads the notebook with nbformat, then flattens each cell into the
shared shape from base.py. Outputs matter as much as code here — a
notebook whose cells were never executed is a common integrity signal,
so we record execution counts and error tracebacks explicitly.
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path
from typing import Any

import nbformat

from backend.parsers.base import (
    MAX_IMAGE_BYTES,
    ParseError,
    empty_result,
    finalize,
)

# Output MIME types we keep, in order of preference for the text channel.
_TEXT_MIMES = ("text/plain", "text/markdown", "text/html")
_IMAGE_MIMES = ("image/png", "image/jpeg", "image/gif", "image/webp")


def _source_to_str(source: Any) -> str:
    """nbformat gives source as either a string or a list of lines."""
    if isinstance(source, list):
        return "".join(source)
    return source or ""


def _flatten_outputs(outputs: list, cell_index: int, images: list) -> tuple[list[str], list[str]]:
    """
    Turn a cell's outputs into (text_outputs, error_tracebacks).
    Images are appended to the shared `images` list as a side effect
    because they belong to the document, not to the cell text.
    """
    texts: list[str] = []
    errors: list[str] = []

    for out in outputs:
        out_type = out.get("output_type")

        if out_type == "stream":
            texts.append(_source_to_str(out.get("text")))

        elif out_type == "error":
            # Traceback is a list of ANSI-coloured lines
            tb = "\n".join(out.get("traceback", []))
            errors.append(f"{out.get('ename')}: {out.get('evalue')}\n{tb}")

        elif out_type in ("execute_result", "display_data"):
            data = out.get("data", {})
            for mime in _TEXT_MIMES:
                if mime in data:
                    texts.append(_source_to_str(data[mime]))
                    break
            for mime in _IMAGE_MIMES:
                if mime in data:
                    payload = _source_to_str(data[mime]).replace("\n", "")
                    # base64 inflates by 4/3 — compare against the decoded size
                    if len(payload) * 3 // 4 <= MAX_IMAGE_BYTES:
                        images.append({
                            "cell_index": cell_index,
                            "media_type": mime,
                            "data_b64": payload,
                        })
                    break

    return texts, errors


def parse(file_path: str | Path) -> dict[str, Any]:
    """Parse a .ipynb file into the shared parse-result shape."""
    path = Path(file_path)
    try:
        # as_version=4 upgrades older notebooks in memory, so we only
        # ever deal with the v4 schema downstream. Student notebooks
        # routinely lack per-cell ids; that is not our problem to fix.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", nbformat.validator.MissingIDFieldWarning)
            nb = nbformat.read(str(path), as_version=4)
    except (nbformat.reader.NotJSONError, json.JSONDecodeError) as exc:
        raise ParseError(f"{path.name} is not valid JSON — is it really a notebook?") from exc
    except Exception as exc:
        raise ParseError(f"Could not read notebook {path.name}: {exc}") from exc

    result = empty_result("ipynb")
    result["metadata"] = {
        "nbformat": f"{nb.get('nbformat')}.{nb.get('nbformat_minor')}",
        "kernel": (nb.get("metadata", {}).get("kernelspec", {}) or {}).get("name"),
        "language": (nb.get("metadata", {}).get("language_info", {}) or {}).get("name"),
    }

    for index, cell in enumerate(nb.get("cells", [])):
        cell_type = cell.get("cell_type", "raw")
        outputs, errors = [], []

        if cell_type == "code":
            outputs, errors = _flatten_outputs(
                cell.get("outputs", []), index, result["images"]
            )
            result["errors"].extend(errors)

        result["cells"].append({
            "index": index,
            "cell_type": cell_type,
            "source": _source_to_str(cell.get("source")),
            "outputs": [t for t in outputs if t.strip()],
            "execution_count": cell.get("execution_count"),
            "has_error": bool(errors),
        })

    # An unexecuted notebook has execution_count None on every code cell.
    code_cells = [c for c in result["cells"] if c["cell_type"] == "code" and c["source"].strip()]
    result["metadata"]["executed"] = any(c["execution_count"] is not None for c in code_cells)

    return finalize(result)
