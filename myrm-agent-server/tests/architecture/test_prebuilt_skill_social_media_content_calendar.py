"""Architecture guard: social-media-content-calendar skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/social-media-content-calendar/SKILL.md

[OUTPUT]
- Architecture tests ensuring social-media-content-calendar skill retains multi-platform matrix, peak engagement windows, and structured calendar contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the social-media-content-calendar prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "social-media-content-calendar"
    / "SKILL.md"
)

_PLATFORM_MARKERS = (
    "X / Twitter",
    "Xiaohongshu",
    "WeChat Official",
    "LinkedIn",
    "Douyin",
)

_CONTRACT_MARKERS = (
    "Date (YYYY-MM-DD)",
    "Time Slot",
    "Content Pillar",
    "Topic & Working Title",
    "Key Hook",
    "Status",
    "file_read_tool",
    "file_write_tool",
)

_MAX_SKILL_CHARS = 10_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing social-media-content-calendar skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_social_media_content_calendar_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_social_media_content_calendar_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"social-media-content-calendar SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_social_media_content_calendar_contains_platforms(skill_text: str) -> None:
    missing = [p for p in _PLATFORM_MARKERS if p not in skill_text]
    assert not missing, f"social-media-content-calendar SKILL.md is missing platforms: {missing}"


def test_social_media_content_calendar_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"social-media-content-calendar SKILL.md is missing contract markers: {missing}"
