"""Architecture test: every app Python package directory declares __init__.py."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_APP_ROOT = _SERVER_ROOT / "app"
_SKIP_DIR_NAMES = frozenset({"__pycache__", "node_modules", ".mypy_cache", ".pytest_cache", ".ruff_cache"})


def _iter_python_package_dirs() -> list[Path]:
    package_dirs: list[Path] = []
    for dirpath in sorted(_APP_ROOT.rglob("*")):
        if not dirpath.is_dir():
            continue
        if any(part in _SKIP_DIR_NAMES for part in dirpath.parts):
            continue
        if not any(child.suffix == ".py" for child in dirpath.iterdir() if child.is_file()):
            continue
        package_dirs.append(dirpath)
    return package_dirs


@pytest.mark.architecture
def test_app_python_dirs_have_init_py() -> None:
    missing: list[str] = []
    for package_dir in _iter_python_package_dirs():
        init_path = package_dir / "__init__.py"
        if not init_path.is_file():
            missing.append(str(package_dir.relative_to(_APP_ROOT)))
    assert not missing, (
        "Python package directories under app/ must include __init__.py:\n"
        + "\n".join(f"  - {rel}" for rel in missing)
    )
