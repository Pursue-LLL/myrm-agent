"""Architecture guard: x-publish-and-schedule skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/x-publish-and-schedule/SKILL.md

[OUTPUT]
- Architecture tests ensuring x-publish-and-schedule retains HITL review gate, character limit checks, and audit receipts

[POS]
Architecture test verifying the operational integrity and contract stability of x-publish-and-schedule skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "x-publish-and-schedule" / "SKILL.md",
    Path(__file__).resolve().parents[4] / "assets" / "prebuilt_skills" / "x-publish-and-schedule" / "SKILL.md",
)
_SKILL_MD = next((p for p in _CANDIDATES if p.is_file()), _CANDIDATES[0])

_CONTRACT_MARKERS = (
    "Mandatory Human-in-the-Loop (HITL) Review",
    "HITL Review Gate",
    "280-character limit",
    "browser_navigate_tool",
    "browser_interact_tool",
    "x_publish_log.jsonl",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing x-publish-and-schedule skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_x_publish_and_schedule_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_x_publish_and_schedule_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"x-publish-and-schedule SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_x_publish_and_schedule_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"x-publish-and-schedule SKILL.md is missing contract markers: {missing}"
