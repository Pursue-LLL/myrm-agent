"""Architecture guard: enterprise-branded-office-handoff skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/enterprise-branded-office-handoff/SKILL.md

[OUTPUT]
- Architecture tests ensuring enterprise-branded-office-handoff retains 3-phase methodology,
  handoff_manifest specification, self-contained directory layout, and zero host-dependency contracts.

[POS]
Architecture test verifying the operational integrity and contract stability of the enterprise-branded-office-handoff prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]
_SKILL_MD = (
    _REPO_ROOT
    / "assets"
    / "prebuilt_skills"
    / "enterprise-branded-office-handoff"
    / "SKILL.md"
)

_CORE_PHASE_MARKERS = (
    "Phase 1: Asset Deconstruction",
    "Phase 2: Skill Encapsulation",
    "Phase 3: Zero-Config Colleague Handoff",
)

_CONTRACT_MARKERS = (
    # Key asset specifications
    "handoff_manifest.yaml",
    "tokens.json",
    "sanitized_sample.pptx",
    "smoke_test_prompt",
    # Methodology & rules
    "Thesis Headline",
    "Design Tokens",
    "Structural Blueprint",
    # Zero-dependency execution
    "python-pptx",
    "docx",
    "openpyxl",
    # Tools in frontmatter
    "file_write_tool",
    "file_read_tool",
    "file_edit_tool",
    "bash_code_execute_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing enterprise-branded-office-handoff skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_enterprise_branded_office_handoff_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_enterprise_branded_office_handoff_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"enterprise-branded-office-handoff SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_enterprise_branded_office_handoff_contains_all_phases(skill_text: str) -> None:
    missing = [m for m in _CORE_PHASE_MARKERS if m not in skill_text]
    assert not missing, f"enterprise-branded-office-handoff SKILL.md is missing phases: {missing}"


def test_enterprise_branded_office_handoff_contains_contract_markers(skill_text: str) -> None:
    missing = [m for m in _CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"enterprise-branded-office-handoff SKILL.md is missing contract markers: {missing}"
