"""Architecture test: myrm-agent-server scripts subtree documented with _ARCH.md."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_SCRIPTS_ROOT = Path(__file__).resolve().parent.parent.parent / "scripts"

_REQUIRED_ARCH_DIRS = (
    _SERVER_SCRIPTS_ROOT,
    _SERVER_SCRIPTS_ROOT / "ci",
    _SERVER_SCRIPTS_ROOT / "dev",
)


@pytest.mark.architecture
@pytest.mark.parametrize("directory", _REQUIRED_ARCH_DIRS, ids=lambda p: p.name)
def test_server_scripts_subtree_has_arch(directory: Path) -> None:
    arch_path = directory / "_ARCH.md"
    assert arch_path.is_file(), f"Missing {arch_path}. See myrm-agent-server/scripts/_ARCH.md for layout."
