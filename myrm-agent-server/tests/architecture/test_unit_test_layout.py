"""Architecture test: forbid tests/unit/**/api/ (importlib collision with tests/api/)."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_TESTS_ROOT = _SERVER_ROOT / "tests"
_UNIT_ROOT = _TESTS_ROOT / "unit"


@pytest.mark.architecture
def test_unit_tree_has_no_api_subpackage() -> None:
    """``import_mode=importlib`` treats ``tests/unit/api`` and ``tests/api`` as one ``api`` package."""
    if not _UNIT_ROOT.is_dir():
        return

    violations = sorted(
        path.relative_to(_TESTS_ROOT).as_posix()
        for path in _UNIT_ROOT.rglob("api")
        if path.is_dir()
    )
    assert not violations, (
        "tests/unit/**/api/ collides with tests/api/ under importlib. "
        "Place unit tests directly under tests/unit/ (e.g. tests/unit/test_system_storage.py):\n"
        + "\n".join(violations)
    )
