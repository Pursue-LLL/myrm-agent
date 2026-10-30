"""Whether a skill's SKILL.md holds other text than a given text: line endings do not count, a missing file is no difference."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.skills.evolution_review.disk_content import skill_file_differs

_STORED = "---\nname: demo-skill\ndescription: As the store has it.\n---\n"
_ON_DISK = "---\nname: demo-skill\ndescription: As the user edited it.\nevolution-locked: true\n---\n"


@pytest.fixture
def skill_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(_ON_DISK, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (_ON_DISK, False),
        (_ON_DISK.replace("\n", "\r\n"), False),
        (_STORED, True),
    ],
)
def test_file_differs_compares_the_text_ignoring_line_endings(skill_file: Path, content: str, expected: bool) -> None:
    assert skill_file_differs(str(skill_file), content) is expected


def test_file_differs_is_false_where_there_is_no_file_to_compare(tmp_path: Path) -> None:
    assert skill_file_differs("", _STORED) is False
    assert skill_file_differs(str(tmp_path / "missing" / "SKILL.md"), _STORED) is False
    assert skill_file_differs(str(tmp_path), _STORED) is False
