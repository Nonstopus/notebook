from __future__ import annotations

import ast
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[1] / "app"


def _contains_tkinter_import(file_path: Path) -> bool:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "tkinter" or alias.name.startswith("tkinter.") for alias in node.names):
                return True
        if isinstance(node, ast.ImportFrom) and node.module:
            if node.module == "tkinter" or node.module.startswith("tkinter."):
                return True
    return False


def test_app_has_no_tkinter_imports():
    offenders = [
        path.relative_to(APP_DIR.parent).as_posix()
        for path in sorted(APP_DIR.rglob("*.py"))
        if _contains_tkinter_import(path)
    ]
    assert not offenders, f"Forbidden tkinter imports found: {', '.join(offenders)}"
