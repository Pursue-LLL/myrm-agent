"""
[POS] tests/unit/test_secret_scanning_ignore_paths.py
[INPUT] pathlib, re, pytest
[OUTPUT] Guard that every `paths-ignore` entry in .github/secret_scanning.yml names an existing single file

GitHub applies `paths-ignore` to secret scanning alerts and to push protection. An entry that
no longer resolves (the fixture was renamed or deleted) silently stops exempting anything, and
a wildcard or directory entry exempts more than the file it was written for.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_ITEM_RE: re.Pattern[str] = re.compile(r"^\s*-\s")
_ENTRY_RE: re.Pattern[str] = re.compile(r'^\s+-\s+"([^"]+)"\s*$')
_WILDCARD_CHARS: frozenset[str] = frozenset("*?[")


def test_secret_scanning_ignore_entries_are_existing_single_files() -> None:
    """Entries are repo-root-relative paths of individual fixture files."""
    repo_root = Path(__file__).resolve().parents[3]
    config = repo_root / ".github" / "secret_scanning.yml"
    if not config.is_file():
        pytest.skip("secret_scanning.yml is not part of this checkout")

    entries: list[str] = []
    violations: list[str] = []
    for line in config.read_text(encoding="utf-8").splitlines():
        if not _ITEM_RE.match(line):
            continue
        if match := _ENTRY_RE.match(line):
            entries.append(match.group(1))
        else:
            # An entry this guard cannot parse would pass unchecked, so it is rejected.
            violations.append(f"{line.strip()}: write each entry as a double-quoted path on its own line")

    violations += [f"{entry}: {reason}" for entry in entries if (reason := _violation(repo_root, entry))]
    assert not violations, "secret_scanning.yml paths-ignore drifted:\n" + "\n".join(violations)


def _violation(repo_root: Path, entry: str) -> str | None:
    if _WILDCARD_CHARS.intersection(entry):
        return "wildcard entries exempt more than one fixture file"
    target = repo_root / entry
    if not target.exists():
        return "path does not exist (renamed or deleted fixture)"
    if not target.is_file():
        return "directory entries exempt more than one fixture file"
    return None
