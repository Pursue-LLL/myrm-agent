"""Architecture test: _ARCH.md must not use lazy placeholder phrases."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_BANNED_PHRASES = (
    "见源码",
)

# Scope: product code trees (exclude .venv, node_modules, caches).
_SCAN_ROOTS = (
    _REPO_ROOT / "myrm-agent-server" / "app",
    _REPO_ROOT / "myrm-agent-frontend" / "src",
    _REPO_ROOT / "myrm-agent-desktop",
    _REPO_ROOT / "myrm-agent-extension",
    _REPO_ROOT / "scripts",
)


def _arch_files_under_roots() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("_ARCH.md"):
            parts = set(path.parts)
            if parts & {"node_modules", ".venv", "__pycache__", ".next"}:
                continue
            files.append(path)
    return sorted(files)


@pytest.mark.architecture
@pytest.mark.parametrize("arch_path", _arch_files_under_roots(), ids=lambda p: p.name)
def test_arch_md_has_no_lazy_placeholders(arch_path: Path) -> None:
    text = arch_path.read_text(encoding="utf-8")
    for phrase in _BANNED_PHRASES:
        if phrase in text:
            rel = arch_path.relative_to(_REPO_ROOT)
            line_no = next(
                (idx for idx, line in enumerate(text.splitlines(), start=1) if phrase in line),
                None,
            )
            pytest.fail(
                f"{rel}:{line_no}: _ARCH.md contains banned placeholder {phrase!r}. "
                "Replace with concrete职责 / I/O/P."
            )
