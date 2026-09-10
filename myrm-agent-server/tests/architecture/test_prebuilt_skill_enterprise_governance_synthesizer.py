"""Architecture guard: enterprise-governance-synthesizer skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/enterprise-governance-synthesizer/SKILL.md

[OUTPUT]
- Architecture tests ensuring enterprise-governance-synthesizer skill retains 4 core governance pillars,
  4-step synthesis SOP, data classification tiers, legal redlines, and yaml output contract.

[POS]
Architecture test verifying the operational integrity and contract stability of the enterprise-governance-synthesizer prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "enterprise-governance-synthesizer"
    / "SKILL.md"
)

_CORE_PILLARS = (
    "enterprise-governance-synthesizer",
    "4 Core Governance Pillars",
    "Brand Tone & Voice Boundaries",
    "Data Security & Classification",
    "Legal & Regulatory Compliance",
    "Escalation & HITL Triggers",
)

_SOP_MARKERS = (
    "Step 1: Ingestion & Document Scanning",
    "Step 2: Tri-Pillar Classification",
    "Step 3: Machine-Readable Rule Formulation",
    "Step 4: Governance Pack Compilation",
)

_CONTRACT_MARKERS = (
    "tier_1_public",
    "tier_2_internal",
    "tier_3_restricted",
    "legal_redlines",
    "escalation_matrix",
)

_TOOL_MARKERS = (
    "file_read_tool",
    "file_write_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing enterprise-governance-synthesizer skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_enterprise_governance_synthesizer_skill_exists_and_bounded(skill_text: str) -> None:
    """Skill file exists, is non-empty, and bounded in size."""
    assert len(skill_text) > 500, "Skill file is unexpectedly short"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"Skill exceeds budget ({len(skill_text)} > {_MAX_SKILL_CHARS}); keep it focused"
    )


def test_enterprise_governance_synthesizer_skill_declares_pillars(skill_text: str) -> None:
    """Skill strictly specifies the 4 core governance pillars."""
    for marker in _CORE_PILLARS:
        assert marker in skill_text, f"Missing pillar marker: {marker}"


def test_enterprise_governance_synthesizer_skill_declares_sop(skill_text: str) -> None:
    """Skill strictly specifies the 4-step synthesis SOP."""
    for marker in _SOP_MARKERS:
        assert marker in skill_text, f"Missing SOP marker: {marker}"


def test_enterprise_governance_synthesizer_skill_declares_contract(skill_text: str) -> None:
    """Skill strictly specifies the contract structure."""
    for marker in _CONTRACT_MARKERS:
        assert marker in skill_text, f"Missing contract marker: {marker}"


def test_enterprise_governance_synthesizer_skill_declares_tools(skill_text: str) -> None:
    """Skill explicitly declares tools in allowed-tools."""
    for marker in _TOOL_MARKERS:
        assert marker in skill_text, f"Missing expected tool in allowed-tools: {marker}"
