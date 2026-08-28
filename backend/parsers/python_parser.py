"""
Plain Python (.py) parser.

A .py file has no cells and no outputs, so we synthesise a single code
cell and additionally walk the AST to extract structure the rubric
engine can check against ("does the submission define train_model()?").

A file with a syntax error still parses — we record the error and grade
what we can, rather than failing the whole submission.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from backend.parsers.base import ParseError, empty_result, finalize


def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render `def foo(a, b=1, *args, **kwargs)` from the AST."""
    args = node.args
    parts: list[str] = []

    positional = args.posonlyargs + args.args
    # Defaults align to the END of the positional list
    pad = len(positional) - len(args.defaults)
    for i, arg in enumerate(positional):
        if i >= pad:
            parts.append(f"{arg.arg}={ast.unparse(args.defaults[i - pad])}")
        else:
            parts.append(arg.arg)
        if args.posonlyargs and i == len(args.posonlyargs) - 1:
            parts.append("/")

    if args.vararg:
        parts.append(f"*{args.vararg.arg}")
    elif args.kwonlyargs:
        parts.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        parts.append(f"{arg.arg}={ast.unparse(default)}" if default else arg.arg)

    if args.kwarg:
        parts.append(f"**{args.kwarg.arg}")

    return f"{node.name}({', '.join(parts)})"


def extract_structure(source: str) -> dict[str, Any]:
    """
    Walk the AST for the structural facts a rubric might ask about.
    Returns `syntax_error` instead of raising so a broken file is still
    gradeable on the parts that do parse.
    """
    structure: dict[str, Any] = {
        "imports": [],
        "functions": [],
        "classes": [],
        "top_level_calls": [],
        "syntax_error": None,
        "docstring": None,
    }

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        structure["syntax_error"] = f"line {exc.lineno}: {exc.msg}"
        return structure

    structure["docstring"] = ast.get_docstring(tree)

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            structure["imports"].extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            structure["imports"].extend(f"{module}.{a.name}" for a in node.names)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            structure["functions"].append({
                "name": node.name,
                "signature": _signature(node),
                "lineno": node.lineno,
                "docstring": ast.get_docstring(node),
                "decorators": [ast.unparse(d) for d in node.decorator_list],
            })
        elif isinstance(node, ast.ClassDef):
            structure["classes"].append({
                "name": node.name,
                "lineno": node.lineno,
                "docstring": ast.get_docstring(node),
                "bases": [ast.unparse(b) for b in node.bases],
                "methods": [
                    n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ],
            })

    # Only direct children of the module count as "top level"
    for node in tree.body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            structure["top_level_calls"].append(ast.unparse(node.value)[:200])

    structure["imports"] = sorted(set(structure["imports"]))
    return structure


def parse(file_path: str | Path) -> dict[str, Any]:
    """Parse a .py file into the shared parse-result shape."""
    path = Path(file_path)
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise ParseError(f"Could not read {path.name}: {exc}") from exc

    result = empty_result("py")
    structure = extract_structure(source)

    result["metadata"] = {"filename": path.name, "structure": structure}
    if structure["syntax_error"]:
        result["errors"].append(f"SyntaxError — {structure['syntax_error']}")

    result["cells"].append({
        "index": 0,
        "cell_type": "code",
        "source": source,
        "outputs": [],
        "execution_count": None,
        "has_error": bool(structure["syntax_error"]),
    })

    # Module docstring reads as the student's written explanation
    if structure["docstring"]:
        result["cells"].append({
            "index": 1,
            "cell_type": "markdown",
            "source": structure["docstring"],
            "outputs": [],
            "execution_count": None,
            "has_error": False,
        })

    return finalize(result)
