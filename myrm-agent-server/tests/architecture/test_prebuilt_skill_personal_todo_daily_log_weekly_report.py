"""Architecture guard: personal-todo-daily-log-weekly-report skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/personal-todo-daily-log-weekly-report/SKILL.md

[OUTPUT]
- Architecture tests ensuring personal-todo-daily-log-weekly-report skill retains three-tier closed loop:
  morning todo triage, evening reconciliation, and weekly synthesis report.

[POS]
Architecture test verifying the operational integrity and contract stability of the personal-todo-daily-log-weekly-report prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "personal-todo-daily-log-weekly-report"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "personal-todo-daily-log-weekly-report",
    "Morning Todo Triage",
    "Evening Log & Reconciliation",
    "Weekly Synthesis Report",
    "P0 必达战果",
    "Key Deliverables & Milestones",
)

_CONTRACT_MARKERS = (
    # Tool definitions
    "file_write_tool",
    "file_read_tool",
    "file_edit_tool",
    # Verification steps
    "daily_log_schema_verified",
    "weekly_report_deliverable_complete",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing personal-todo-daily-log-weekly-report skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_personal_todo_daily_log_weekly_report_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_personal_todo_daily_log_weekly_report_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"personal-todo-daily-log-weekly-report SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_personal_todo_daily_log_weekly_report_contains_core_markers(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"personal-todo-daily-log-weekly-report SKILL.md is missing core markers: {missing}"


def test_personal_todo_daily_log_weekly_report_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"personal-todo-daily-log-weekly-report SKILL.md is missing contract markers: {missing}"
