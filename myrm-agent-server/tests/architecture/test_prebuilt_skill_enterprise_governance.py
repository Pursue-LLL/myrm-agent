"""Architecture guard: enterprise-governance skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/enterprise-governance/SKILL.md

[OUTPUT]
- Architecture tests ensuring enterprise-governance skill retains 4 core pillars, L1-L4 data classification, and machine-auditable rule contracts.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "enterprise-governance"
    / "SKILL.md"
)

_CORE_PILLARS = (
    "Pillar 1: Brand Voice",
    "Pillar 2: Data Security & Confidentiality Classification",
    "Pillar 3: Legal & Regulatory Compliance",
    "Pillar 4: AI-Native Safe SDLC Guardrails",
)

_CLASSIFICATION_LEVELS = (
    "L1",
    "L2",
    "L3",
    "L4",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing enterprise-governance skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_enterprise_governance_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_enterprise_governance_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"enterprise-governance SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_enterprise_governance_contains_all_pillars(skill_text: str) -> None:
    missing = [p for p in _CORE_PILLARS if p not in skill_text]
    assert not missing, f"enterprise-governance SKILL.md missing pillars: {missing}"


def test_enterprise_governance_contains_classification_levels(skill_text: str) -> None:
    missing = [c for c in _CLASSIFICATION_LEVELS if c not in skill_text]
    assert not missing, f"enterprise-governance SKILL.md missing classification levels: {missing}"
