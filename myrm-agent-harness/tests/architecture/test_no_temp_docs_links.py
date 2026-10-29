"""Architecture test: tracked markdown must not point into the private dev-shell planning docs."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Reference kinds that resolve only inside the private dev shell: relative paths into
# temp-docs/ and planning item ids (topic_NN).
_PRIVATE_REFERENCES = (
    ("private dev-shell path", re.compile(r"temp-docs/[A-Za-z0-9_./-]+")),
    ("private planning item id", re.compile(r"\btopic_[0-9]{2}(?![0-9])")),
)


def _tracked_markdown_files() -> list[Path]:
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "*.md"],
        cwd=_REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return [_REPO_ROOT / p for p in paths]


@pytest.mark.parametrize("path", _tracked_markdown_files(), ids=lambda p: p.name)
def test_no_private_planning_references(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(_REPO_ROOT)
    for line_no, line in enumerate(text.splitlines(), start=1):
        for kind, pattern in _PRIVATE_REFERENCES:
            match = pattern.search(line)
            if match:
                pytest.fail(
                    f"{rel}:{line_no}: references {kind} {match.group()!r}. "
                    "Use in-repo _ARCH.md or maintainer-only notes without path links."
                )
