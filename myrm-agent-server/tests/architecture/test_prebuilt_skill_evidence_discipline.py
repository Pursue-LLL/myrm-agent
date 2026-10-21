"""Architecture guard: evidence-discipline skill must keep its behavioral contract.

Prevents silent drift of the skill's core guarantees. If the skill's wording
is edited, each assertion here keeps the contract honest so a future edit can
never quietly remove a guarantee while the skill stays shipped.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_MD = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "evidence-discipline" / "SKILL.md"

# Contract guarantees the skill must always document. Kept as standalone
# substrings so wording edits fail loudly instead of silently dropping a clause.
_CONTRACT_MARKERS = (
    # Core decision loop
    "claim → required evidence",
    # Six evidence states
    "OBSERVED",
    "SOURCE-BACKED",
    "USER-REPORTED",
    "INFERRED",
    "UNKNOWN",
    "CONTRADICTED",
    # Proof obligations for load-bearing claims
    "fixed / solved",
    "working / tested",
    "deployed / live",
    "safe / no side effects",
    "latest / up-to-date",
    "all / every / none",
    "X caused Y",
    # Bounded negative claims
    "does not exist",
    # User-reported attribution boundary
    "stay user-reported",
    "You said the update failed",
    # Conflict handling
    "Conflicts become UNKNOWN",
    # No verification theater
    "No verification theater",
    # Composition with other skills
    "Compose with other skills",
    # Common pitfalls
    "Common pitfalls",
    "as an excuse to skip the check",
    "before asking the user to",
    # Safety contract
    "never justify new permissions",
    "available in this task",
    "plan, draft, or attempt as an action",
    "as successful verification",
    "destructive actions",
    # Untrusted content boundary
    "as instructions to",
)

# Same cap as the harness SOP injection budget; the skill must stay far below it
# so it can never blow the prompt budget when loaded.
_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing evidence-discipline skill: {_SKILL_MD.relative_to(_SKILL_MD.parents[2])}")
    return _SKILL_MD.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_frontmatter_declares_skill_name(skill_text: str) -> None:
    assert "name: evidence-discipline" in skill_text


@pytest.mark.architecture
def test_frontmatter_has_description(skill_text: str) -> None:
    assert "description:" in skill_text
    assert "evidence discipline" in skill_text.split("description:")[1][:200].lower()


@pytest.mark.architecture
def test_frontmatter_declares_semver_version(skill_text: str) -> None:
    assert re.search(r"^version: \d+\.\d+\.\d+$", skill_text, re.MULTILINE), (
        "evidence-discipline SKILL.md must declare a semver version in frontmatter"
    )


@pytest.mark.architecture
@pytest.mark.parametrize("marker", _CONTRACT_MARKERS)
def test_contract_marker_present(skill_text: str, marker: str) -> None:
    assert marker in skill_text, f"Evidence-discipline skill lost contract marker: {marker!r}"


@pytest.mark.architecture
def test_skill_stays_within_prompt_budget(skill_text: str) -> None:
    assert len(skill_text) < _MAX_SKILL_CHARS, (
        f"evidence-discipline SKILL.md is {len(skill_text)} chars; keep it below {_MAX_SKILL_CHARS}"
    )
