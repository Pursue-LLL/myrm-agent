"""Architecture guard: voice-corpus-review skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/voice-corpus-review/SKILL.md

[OUTPUT]
- Architecture tests ensuring voice-corpus-review skill retains multi-corpus search, kanban cross-audit, blocker attribution, and artifact contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the voice-corpus-review prebuilt skill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "voice-corpus-review"
    / "SKILL.md"
)

_CONTRACT_MARKERS = (
    # Core operating dimensions
    "Multi-Corpus Semantic Retrieval",
    "Kanban Reality Cross-Audit",
    "Blocker Attribution & Root-Cause Analysis",
    "Review Report Artifact Generation",
    # Specific tool bindings & parameters
    'corpus="all"',
    'status_filter="blocked"',
    "memory_search_tool",
    "kanban_list_tasks",
    "file_write_tool",
    # Artifact destination and structure
    "docs/reviews/",
    "Critical Blockers",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing voice-corpus-review skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_frontmatter_declares_skill_name(skill_text: str) -> None:
    assert "name: voice-corpus-review" in skill_text


@pytest.mark.architecture
def test_frontmatter_has_description(skill_text: str) -> None:
    assert "description:" in skill_text
    assert "voice corpus" in skill_text.split("description:")[1][:250].lower()


@pytest.mark.architecture
def test_frontmatter_declares_semver_version(skill_text: str) -> None:
    assert re.search(r"^version: \d+\.\d+\.\d+$", skill_text, re.MULTILINE), (
        "voice-corpus-review SKILL.md must declare a semver 'version: x.y.z'"
    )


@pytest.mark.architecture
@pytest.mark.parametrize("marker", _CONTRACT_MARKERS)
def test_contract_marker_present(skill_text: str, marker: str) -> None:
    assert marker in skill_text, (
        f"Required contract marker missing from voice-corpus-review SKILL.md: {marker!r}"
    )


@pytest.mark.architecture
def test_skill_size_within_budget(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"voice-corpus-review SKILL.md is {len(skill_text)} chars, exceeding budget {_MAX_SKILL_CHARS}"
    )


@pytest.mark.architecture
def test_channel_router_review_week_command_registered() -> None:
    from app.channels.routing.command_defs import SYSTEM_COMMANDS, CommandKind

    review_cmd = next((c for c in SYSTEM_COMMANDS if c.name == "review-week"), None)
    assert review_cmd is not None, "Missing /review-week command in SYSTEM_COMMANDS"
    assert review_cmd.kind == CommandKind.SKILL
    assert "voice-corpus-review" in review_cmd.skill_ids
    assert "extract-blockers" in review_cmd.aliases
    assert "week-review" in review_cmd.aliases
    assert "weekly-digest" in review_cmd.aliases
