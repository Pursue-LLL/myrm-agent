"""Architecture guard: customer-relationship-draft-review skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/customer-relationship-draft-review/SKILL.md

[OUTPUT]
- Architecture tests ensuring customer-relationship-draft-review skill retains HITL human signoff,
  quadruple safety gates (pricing, sensitive pii, commitments, tone sentiment), zero unreviewed outbound rule,
  and structured review card schema.

[POS]
Architecture test verifying the operational integrity and contract stability of the customer-relationship-draft-review prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "customer-relationship-draft-review"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "customer-relationship-draft-review",
    "Human-in-the-Loop",
    "Commitment Audit",
    "PRICING_GATE",
    "PII_LEAK_GATE",
    "COMMITMENT_GATE",
    "SENTIMENT_GATE",
)

_SAFETY_CONTRACT_MARKERS = (
    # Zero unreviewed outbound transmission rule
    "NEVER",
    "Proposed Draft",
    "Operator Action Options",
    # Four-phase SOP markers
    "Phase 1: Context & Intent Extraction",
    "Phase 2: High-Quality Draft Synthesis",
    "Phase 3: Quadruple Safety Audit",
    "Phase 4: Structured HITL Packaging",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing customer-relationship-draft-review skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_customer_relationship_draft_review_skill_exists_and_bounded(skill_text: str) -> None:
    assert len(skill_text) > 500, "Skill content is suspiciously short"
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"Skill content ({len(skill_text)} chars) exceeds budget ({_MAX_SKILL_CHARS})"
    )


def test_customer_relationship_draft_review_frontmatter_contract(skill_text: str) -> None:
    assert skill_text.startswith("---"), "Missing frontmatter start"
    assert "name: customer-relationship-draft-review" in skill_text
    assert "category: business" in skill_text
    assert "contract:" in skill_text
    assert "potential_traps:" in skill_text
    assert "verification_steps:" in skill_text


def test_customer_relationship_draft_review_core_markers_present(skill_text: str) -> None:
    missing = [m for m in _CORE_MODULE_MARKERS if m not in skill_text]
    assert not missing, f"Missing core markers in skill: {missing}"


def test_customer_relationship_draft_review_safety_contract_markers_present(skill_text: str) -> None:
    missing = [m for m in _SAFETY_CONTRACT_MARKERS if m not in skill_text]
    assert not missing, f"Missing safety contract markers in skill: {missing}"
