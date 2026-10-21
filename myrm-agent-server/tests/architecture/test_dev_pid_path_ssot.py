"""Architecture test: dev stack pid reads must use MYRM_DEV_STATE_DIR only.

Subdirectory ``.myrm-dev-*`` paths may appear only in cleanup (rm) or gitignore docs.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_SCRIPTS_ROOT = _REPO_ROOT / "scripts"

_LEGACY_PID_READ = re.compile(
    r"\.myrm-dev-(?:backend|frontend)\.pid|"
    r"myrm-dev-backend\.pid|myrm-dev-frontend\.pid"
)

_SCAN_SUFFIXES = {".sh", ".py", ".ps1", ".mjs"}

# Paths allowed to mention legacy filenames (cleanup rm, not read).
_ALLOWLIST_REL: frozenset[str] = frozenset(
    {
        "scripts/dev/lib/dev_state_paths.sh",
        "scripts/myrm",
        "scripts/myrm.ps1",
        "scripts/dev/dev.ps1",
        "scripts/dev/start.ps1",
    }
)

# Line-level exemptions: cleanup/remove only.
_CLEANUP_LINE = re.compile(r"\b(rm\s+-f|Remove-Item|cleanup_legacy)")


def _iter_script_files() -> list[Path]:
    files: list[Path] = []
    for path in sorted(_SCRIPTS_ROOT.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix not in _SCAN_SUFFIXES:
            continue
        if "__pycache__" in path.parts:
            continue
        files.append(path)
    return files


def _is_allowed_line(rel: str, line: str) -> bool:
    if rel == "scripts/dev/lib/dev_state_paths.sh":
        return True
    if rel in _ALLOWLIST_REL and _CLEANUP_LINE.search(line):
        return True
    return False


@pytest.mark.parametrize("path", _iter_script_files(), ids=lambda p: p.relative_to(_REPO_ROOT).as_posix())
def test_no_legacy_dev_pid_reads(path: Path) -> None:
    rel = path.relative_to(_REPO_ROOT).as_posix()
    text = path.read_text(encoding="utf-8", errors="replace")
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _LEGACY_PID_READ.search(line) and not _is_allowed_line(rel, line):
            pytest.fail(
                f"{rel}:{line_no}: legacy dev pid path {line.strip()!r}. "
                "Read ~/.local/state/myrm-dev/{{backend,frontend}}.pid via dev_state_paths "
                "or stack_supervisor.paths.resolve_paths()."
            )
