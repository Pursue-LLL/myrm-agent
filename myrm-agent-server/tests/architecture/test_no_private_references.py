"""Architecture test: tracked text files must not point into the private dev shell."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
# Reference kinds that resolve only inside the private dev shell: relative paths into the
# planning directory and planning item ids. The id alternative uses explicit non-word
# boundaries instead of \b so an id glued to CJK text is still caught, while chat topic
# keys (leading underscore) and longer digit runs are not.
_PRIVATE_REFERENCE_PATTERN = r"temp-docs/[A-Za-z0-9_./-]+|(^|[^A-Za-z0-9_])topic_[0-9]{2}([^0-9]|$)"
_MAX_REPORTED_HITS = 20

# Samples are assembled from fragments so this file does not match its own pattern.
_DIR = "temp-" + "docs"
_ID = "topic" + "_12"
_PATTERN_CASES = [
    pytest.param(f"see {_DIR}/roadmap/a.md for details", True, id="path"),
    pytest.param(f"{_ID} is planned", True, id="id-at-line-start"),
    pytest.param(f"ends with {_ID}", True, id="id-at-line-end"),
    pytest.param(f"planned in ({_ID})", True, id="id-in-parentheses"),
    pytest.param(f"条目{_ID}已完成", True, id="id-glued-to-cjk"),
    pytest.param(f"prose names {_DIR}/ only", False, id="directory-name-without-path"),
    pytest.param(f"chat key _{_ID}", False, id="chat-topic-key"),
    pytest.param(f"my{_ID}", False, id="id-inside-a-word"),
    pytest.param(f"{_ID}3", False, id="three-digit-number"),
]


def _git_grep(args: list[str], cwd: Path) -> list[str]:
    """Return ``path:line:text`` rows matching the private-reference pattern (status 1 means none)."""
    result = subprocess.run(
        ["git", "grep", "-I", "-n", "-E", "-e", _PRIVATE_REFERENCE_PATTERN, *args],
        cwd=cwd,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed with status {result.returncode}: {result.stderr.strip()}")
    return result.stdout.splitlines()


@pytest.mark.parametrize(("line", "expected"), _PATTERN_CASES)
def test_pattern_matches_exactly_the_private_reference_shapes(line: str, expected: bool, tmp_path: Path) -> None:
    sample = tmp_path / "sample.txt"
    sample.write_text(line + "\n", encoding="utf-8")
    assert bool(_git_grep(["--no-index", "--", sample.name], cwd=tmp_path)) is expected


def test_tracked_text_files_have_no_private_references() -> None:
    hits = _git_grep(["--", "."], cwd=_REPO_ROOT)
    if not hits:
        return
    detail = "\n".join(row[:200] for row in hits[:_MAX_REPORTED_HITS])
    if len(hits) > _MAX_REPORTED_HITS:
        detail += f"\n... and {len(hits) - _MAX_REPORTED_HITS} more"
    pytest.fail(
        "Tracked files reference the private dev shell (planning paths or item ids that resolve nowhere in this repo). "
        "Use in-repo _ARCH.md or brand docs instead.\n" + detail
    )
