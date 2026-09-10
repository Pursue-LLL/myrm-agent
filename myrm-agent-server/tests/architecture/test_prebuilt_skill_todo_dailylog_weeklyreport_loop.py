"""Architecture guard: todo-dailylog-weeklyreport-loop skill contract stability.

[INPUT]
- assets/prebuilt_skills/todo-dailylog-weeklyreport-loop/SKILL.md

[OUTPUT]
- Architecture tests ensuring todo-dailylog-weeklyreport-loop retains the 4-phase rhythm, daily log schema, pyramid weekly report specification, and allowed tools.

[POS]
Architecture test verifying the operational integrity and contract stability of the personal closed loop productivity prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

_CANDIDATE_PATHS = [
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "todo-dailylog-weeklyreport-loop"
    / "SKILL.md",
    Path(__file__).resolve().parents[4]
    / "assets"
    / "prebuilt_skills"
    / "todo-dailylog-weeklyreport-loop"
    / "SKILL.md",
]


def _find_skill_md() -> Path:
    for path in _CANDIDATE_PATHS:
        if path.is_file():
            return path
    pytest.fail(f"Could not find todo-dailylog-weeklyreport-loop SKILL.md in candidates: {_CANDIDATE_PATHS}")


_REQUIRED_PHASES = (
    "Phase 1: Morning Focus",
    "Phase 2: Execution & Proof",
    "Phase 3: Evening Reconciliation",
    "Phase 4: Friday Weekly Synthesis",
)

_REQUIRED_DAILY_LOG_SECTIONS = (
    "今日焦点对账",
    "关键产出与证据链",
    "阻塞与卡点",
    "明日计划",
)

_REQUIRED_WEEKLY_REPORT_SECTIONS = (
    "本周核心战果概览",
    "重点项目交付详情",
    "关键指标异动与复盘",
    "下周核心计划",
)

_ALLOWED_TOOLS = (
    "kanban_manage_tool",
    "memory_save_tool",
    "memory_search_tool",
    "file_write_tool",
    "file_read_tool",
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    path = _find_skill_md()
    return path.read_text(encoding="utf-8")


def test_todo_dailylog_weeklyreport_loop_file_exists() -> None:
    path = _find_skill_md()
    assert path.is_file(), f"File does not exist: {path}"


def test_todo_dailylog_weeklyreport_loop_frontmatter(skill_text: str) -> None:
    parts = skill_text.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must have valid YAML frontmatter between --- delimiters"
    meta = yaml.safe_load(parts[1])
    assert meta.get("name") == "todo-dailylog-weeklyreport-loop"
    assert meta.get("category") == "productivity"
    assert "todo" in meta.get("tags", [])
    assert "weekly-report" in meta.get("tags", [])

    tools = meta.get("allowed-tools", [])
    for tool in _ALLOWED_TOOLS:
        assert tool in tools, f"Missing allowed tool: {tool}"


def test_todo_dailylog_weeklyreport_loop_phases(skill_text: str) -> None:
    for phase in _REQUIRED_PHASES:
        assert phase in skill_text, f"Missing operating rhythm phase: {phase}"


def test_todo_dailylog_weeklyreport_loop_specifications(skill_text: str) -> None:
    for sec in _REQUIRED_DAILY_LOG_SECTIONS:
        assert sec in skill_text, f"Missing daily log specification section: {sec}"

    for sec in _REQUIRED_WEEKLY_REPORT_SECTIONS:
        assert sec in skill_text, f"Missing weekly report specification section: {sec}"
