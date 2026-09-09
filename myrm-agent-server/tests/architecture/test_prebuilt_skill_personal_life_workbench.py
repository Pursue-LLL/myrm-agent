"""Architecture guard: personal-life-workbench skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/personal-life-workbench/SKILL.md

[OUTPUT]
- Architecture tests ensuring personal-life-workbench skill retains 8 modular blocks, host theme bridge binding, zero external dependencies, and local state persistence contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the personal-life-workbench prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "personal-life-workbench"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "Focus Todos",
    "Habit Streaks",
    "Pomodoro Timer",
    "Quick Notes",
    "Daily Reflection",
    "Hydration Log",
    "Launchpad",
    "Countdown Tracker",
)

_CONTRACT_MARKERS = (
    # Host theme integration
    "var(--background",
    "var(--card",
    "var(--border",
    "var(--primary",
    # Zero external dependency & offline first
    "localStorage",
    "JSON.stringify",
    "JSON.parse",
    # Tool declarations in frontmatter
    "file_write_tool",
    "file_read_tool",
)

_MAX_SKILL_CHARS = 16_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing personal-life-workbench skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_personal_life_workbench_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_personal_life_workbench_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"personal-life-workbench SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_personal_life_workbench_contains_all_modules(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"personal-life-workbench SKILL.md is missing modules: {missing}"


def test_personal_life_workbench_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"personal-life-workbench SKILL.md is missing contract markers: {missing}"
