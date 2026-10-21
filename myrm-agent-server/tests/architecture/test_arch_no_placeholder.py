"""Architecture test: _ARCH.md must not use lazy placeholder phrases."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_BANNED_PHRASES = (
    "见源码",
    "本目录模块说明",
)

# Scope: product code trees (exclude .venv, node_modules, caches, build targets).
_SCAN_ROOTS = (
    _REPO_ROOT / "myrm-agent-server" / "app",
    _REPO_ROOT / "myrm-agent-frontend" / "src",
    _REPO_ROOT / "myrm-agent-desktop",
    _REPO_ROOT / "myrm-agent-extension",
    _REPO_ROOT / "scripts",
)
_SKIP_DIRNAMES = frozenset({"node_modules", ".venv", "__pycache__", ".next", "target", "dist", "build", ".git"})


def _arch_files_under_roots() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRNAMES]
            if "_ARCH.md" in filenames:
                files.append(Path(dirpath) / "_ARCH.md")
    return sorted(files)


@pytest.mark.architecture
def test_arch_md_has_no_lazy_placeholders() -> None:
    violations: list[str] = []
    for arch_path in _arch_files_under_roots():
        text = arch_path.read_text(encoding="utf-8")
        for phrase in _BANNED_PHRASES:
            if phrase in text:
                rel = arch_path.relative_to(_REPO_ROOT)
                line_no = next(
                    (idx for idx, line in enumerate(text.splitlines(), start=1) if phrase in line),
                    None,
                )
                violations.append(
                    f"{rel}:{line_no}: _ARCH.md contains banned placeholder {phrase!r}. Replace with concrete职责 / I/O/P."
                )
    assert not violations, "\n".join(violations)
