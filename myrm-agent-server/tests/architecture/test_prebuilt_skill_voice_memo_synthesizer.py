"""Architecture guard: voice-memo-synthesizer skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/voice-memo-synthesizer/SKILL.md

[OUTPUT]
- Architecture tests ensuring voice-memo-synthesizer skill retains 4D decomposition, actionability threshold, idempotency, and artifact contracts

[POS]
Architecture test verifying the operational integrity and contract stability of the voice-memo-synthesizer prebuilt skill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "voice-memo-synthesizer"
    / "SKILL.md"
)

_CONTRACT_MARKERS = (
    # Core operating dimensions
    "Meeting Minutes Artifact",
    "Actionable Kanban Tasks",
    "Long-Term Memory Facts",
    "Structured Spreadsheet Artifact",
    # Actionability threshold & board resolution
    "Actionability Threshold",
    "Threshold Gating Rule",
    "Board Resolution Protocol",
    "kanban_list_tasks(limit=1)",
    # Idempotency and encoding
    "Deterministic Idempotency Key",
    "idempotency_key",
    "utf-8-sig",
    # Tool declarations in frontmatter
    "file_write_tool",
    "kanban_add_task",
    "memory_save_tool",
    "bash_code_execute_tool",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing voice-memo-synthesizer skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_frontmatter_declares_skill_name(skill_text: str) -> None:
    assert "name: voice-memo-synthesizer" in skill_text


@pytest.mark.architecture
def test_frontmatter_has_description(skill_text: str) -> None:
    assert "description:" in skill_text
    assert "voice memo" in skill_text.split("description:")[1][:250].lower()


@pytest.mark.architecture
def test_frontmatter_declares_semver_version(skill_text: str) -> None:
    assert re.search(r"^version: \d+\.\d+\.\d+$", skill_text, re.MULTILINE), (
        "voice-memo-synthesizer SKILL.md must declare a semver 'version: x.y.z'"
    )


@pytest.mark.architecture
@pytest.mark.parametrize("marker", _CONTRACT_MARKERS)
def test_contract_marker_present(skill_text: str, marker: str) -> None:
    assert marker in skill_text, (
        f"Required contract marker missing from voice-memo-synthesizer SKILL.md: {marker!r}"
    )


@pytest.mark.architecture
def test_skill_size_within_budget(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"voice-memo-synthesizer SKILL.md is {len(skill_text)} chars, exceeding budget {_MAX_SKILL_CHARS}"
    )
