"""Architecture guard: sesa-veriskill-memory skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/sesa-veriskill-memory/SKILL.md

[OUTPUT]
- Architecture tests ensuring sesa-veriskill-memory skill retains 4-way causal attribution matrix, Help-Hurt net-score pruning protocol, and benchmark verification gates.

[POS]
Architecture test verifying the operational integrity and contract stability of the sesa-veriskill-memory prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "sesa-veriskill-memory"
    / "SKILL.md"
)

_CORE_FAILURE_CATEGORIES = (
    "Environmental Transient",
    "Tool Interface Defect",
    "Missing Domain Knowledge",
    "Skill SOP Flaw",
)

_CONTRACT_MARKERS = (
    "Help-Hurt Net-Score Pruning Protocol",
    "Delta Net-Score",
    "Promotion Threshold",
    "file_read_tool",
    "file_write_tool",
    "bash_code_execute_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing sesa-veriskill-memory skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_sesa_veriskill_memory_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_sesa_veriskill_memory_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"sesa-veriskill-memory SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_sesa_veriskill_memory_contains_all_categories(skill_text: str) -> None:
    missing = [c for c in _CORE_FAILURE_CATEGORIES if c not in skill_text]
    assert not missing, f"sesa-veriskill-memory SKILL.md is missing failure categories: {missing}"


def test_sesa_veriskill_memory_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"sesa-veriskill-memory SKILL.md is missing contract markers: {missing}"
