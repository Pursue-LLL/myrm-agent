"""Architecture test: OSS scripts subtree documented with _ARCH.md."""

from __future__ import annotations

from pathlib import Path

import pytest

_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "scripts"

_REQUIRED_ARCH_DIRS = (
    _SCRIPTS_ROOT,
    _SCRIPTS_ROOT / "ci",
    _SCRIPTS_ROOT / "dev",
    _SCRIPTS_ROOT / "lib",
    _SCRIPTS_ROOT / "dev" / "lib",
)


@pytest.mark.architecture
@pytest.mark.parametrize("directory", _REQUIRED_ARCH_DIRS, ids=lambda p: p.name)
def test_scripts_subtree_has_arch(directory: Path) -> None:
    arch_path = directory / "_ARCH.md"
    assert arch_path.is_file(), f"Missing {arch_path}. See scripts/_ARCH.md for layout."
