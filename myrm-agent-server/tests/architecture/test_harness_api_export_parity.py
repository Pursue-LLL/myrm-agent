"""Every harness public-API symbol referenced by server code must be exported.

Guards the cross-layer contract that broke the dev stack (server imported
``DesktopCaptureDriver`` from ``myrm_agent_harness.api`` after a harness-internal
refactor removed it from the public surface, crashing backend startup with
``ImportError``).

``tests/api/test_public_surface.py`` inside the harness only asserts that
``api.__all__`` matches ``api._EXPORTS`` and that listed names resolve — it can
never detect a *consumer* referencing a symbol the harness forgot to export.
This gate closes that blind spot from the consumer side.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_SCAN_DIRS = (_SERVER_ROOT / "app", _SERVER_ROOT / "tests")
_SKIP_DIR_NAMES = frozenset({".venv", "__pycache__", "node_modules"})
_HARNESS_API_MODULE = "myrm_agent_harness.api"
_HARNESS_ROOT_MODULE = "myrm_agent_harness"
_HARNESS_API_ATTR = "api"


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for base in _SCAN_DIRS:
        if not base.is_dir():
            continue
        for path in base.rglob("*.py"):
            if _SKIP_DIR_NAMES.intersection(path.parts):
                continue
            files.append(path)
    return sorted(files)


def _referenced_symbols(tree: ast.AST) -> set[str]:
    """Symbols accessed as ``myrm_agent_harness.api`` members."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            # ``from myrm_agent_harness.api import X, Y``
            if node.module == _HARNESS_API_MODULE:
                names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Attribute):
            # ``myrm_agent_harness.api.X``
            base = node.value
            if (
                isinstance(base, ast.Attribute)
                and isinstance(base.value, ast.Name)
                and base.value.id == _HARNESS_ROOT_MODULE
                and base.attr == _HARNESS_API_ATTR
            ):
                names.add(node.attr)
    return names


def test_server_references_only_exported_harness_api_symbols() -> None:
    harness_api = pytest.importorskip(
        _HARNESS_API_MODULE,
        reason="harness not importable in this environment",
    )
    exported = set(harness_api.__all__)

    referenced: dict[str, set[str]] = {}
    for path in _iter_python_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (SyntaxError, UnicodeDecodeError, OSError):
            # Unparseable sources are outside this gate's scope.
            continue
        for symbol in _referenced_symbols(tree):
            referenced.setdefault(symbol, set()).add(str(path.relative_to(_SERVER_ROOT)))

    missing = {name: files for name, files in referenced.items() if name not in exported}

    assert not missing, (
        "Server references myrm_agent_harness.api symbols that the harness does not "
        "export (backend startup fails with ImportError):\n"
        + "\n".join(
            f"  {name} <- {', '.join(sorted(missing[name]))}"
            for name in sorted(missing)
        )
        + "\nFix: add the symbol to `_EXPORTS` and `__all__` in "
        "myrm-agent-harness/src/myrm_agent_harness/api/__init__.py"
    )
