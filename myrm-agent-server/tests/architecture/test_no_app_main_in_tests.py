"""Architecture test: tests must not import app.main (use build_minimal_app instead)."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_TESTS_ROOT = _SERVER_ROOT / "tests"


def _collect_app_main_imports() -> list[str]:
    violations: list[str] = []
    for path in sorted(_TESTS_ROOT.rglob("*.py")):
        rel = path.relative_to(_SERVER_ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=rel)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "app.main" or alias.name.startswith("app.main."):
                        violations.append(f"{rel}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module == "app.main" or node.module.startswith("app.main."):
                    violations.append(f"{rel}:{node.lineno}: from {node.module} import ...")
    return violations


@pytest.mark.architecture
def test_tests_do_not_import_app_main() -> None:
    """API/integration tests must use tests.support.minimal_app, not app.main."""
    violations = _collect_app_main_imports()
    assert not violations, (
        "tests/** must not import app.main (pulls full dependency stack ~439MB). "
        "Use build_minimal_app(preset=...) from tests.support.minimal_app:\n" + "\n".join(violations)
    )
