"""Architecture guard: enterprise-branded-office skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/enterprise-branded-office/SKILL.md

[OUTPUT]
- Architecture tests ensuring enterprise-branded-office skill retains the 3 deliverable pillars, 4-step wizard protocol, zero-config colleague handoff, and tool contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the enterprise-branded-office prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "enterprise-branded-office"
    / "SKILL.md"
)

_CORE_PILLARS = (
    "Corporate Presentation",
    "Formal Executive Document",
    "Financial & Operations Spreadsheet",
    "python-pptx",
    "python-docx",
    "openpyxl",
)

_CONTRACT_MARKERS = (
    "Template Context & Brand Asset Harvesting",
    "Design System Crystallization",
    "Self-Contained Automation Scaffolding",
    "Zero-Config Colleague Handoff",
    "Anti-Pattern & Compliance Rules",
    "file_write_tool",
    "file_read_tool",
    "file_edit_tool",
    "bash_code_execute_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing enterprise-branded-office skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_enterprise_branded_office_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_enterprise_branded_office_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"enterprise-branded-office SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_enterprise_branded_office_contains_core_pillars(skill_text: str) -> None:
    missing = [m for m in _CORE_PILLARS if m not in skill_text]
    assert not missing, f"enterprise-branded-office SKILL.md is missing core pillars: {missing}"


def test_enterprise_branded_office_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"enterprise-branded-office SKILL.md is missing contract markers: {missing}"
