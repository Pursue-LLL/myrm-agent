"""Architecture test: core/services/lifecycle must not import app.api."""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_APP_ROOT = _SERVER_ROOT / "app"
_BASELINE_PATH = Path(__file__).resolve().parent / "data" / "server_api_import_baseline.txt"
_GUARDED_PREFIXES = ("core/", "services/", "lifecycle/")


def _is_guarded(rel_path: str) -> bool:
    return rel_path.startswith(_GUARDED_PREFIXES)


def _collect_api_imports() -> frozenset[str]:
    imports: set[str] = set()
    for path in _APP_ROOT.rglob("*.py"):
        rel = path.relative_to(_APP_ROOT).as_posix()
        if not _is_guarded(rel):
            continue
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            match = re.match(r"^\s*(?:from|import)\s+(app\.api[^\s#]+)", line)
            if match:
                imports.add(f"{rel}:{match.group(1)}")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("app.api"):
                        imports.add(f"{rel}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("app.api"):
                imports.add(f"{rel}:{node.module}")
    return frozenset(imports)


def _load_baseline() -> frozenset[str]:
    if not _BASELINE_PATH.is_file():
        return frozenset()
    return frozenset(
        line.strip()
        for line in _BASELINE_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    )


@pytest.mark.architecture
def test_no_core_services_lifecycle_imports_app_api() -> None:
    """Business layers must not depend on HTTP routers or FastAPI DI shims."""
    baseline = _load_baseline()
    current = _collect_api_imports()
    new_imports = sorted(current - baseline)
    assert not new_imports, (
        "New app.api imports detected under app/core, app/services, or app/lifecycle. "
        "Move shared code to app/schemas, app/services, or app/core:\n" + "\n".join(new_imports)
    )
    assert not current, (
        "app.api imports remain under guarded layers (baseline must stay empty):\n"
        + "\n".join(sorted(current))
    )
