"""Architecture guard: deprecated-plugin-migration skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/deprecated-plugin-migration/SKILL.md

[OUTPUT]
- Architecture tests ensuring deprecated-plugin-migration skill retains 4-phase auto-fix pipeline, deprecation mapping rules, and backup safety protocols.

[POS]
Architecture test verifying the operational integrity and contract stability of the deprecated-plugin-migration prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_SKILL_MD = (
    Path(__file__).resolve().parents[3]
    / "assets"
    / "prebuilt_skills"
    / "deprecated-plugin-migration"
    / "SKILL.md"
)

_PHASE_MARKERS = (
    "Phase 1: Deprecation Scanning",
    "Phase 2: In-Memory AST & Schema Migration",
    "Phase 3: Diff Generation & Safety Backup",
    "Phase 4: Atomic In-Place Patching & Doctor Verification",
)

_SECTION_MARKERS = (
    "Deprecation Mapping Rules",
    "The 4-Phase Auto-Fix Pipeline",
    "Standard Execution SOP",
)

_MAX_SKILL_CHARS = 12_000


@pytest.fixture(scope="module")
def skill_text() -> str:
    if not _SKILL_MD.is_file():
        pytest.fail(f"Missing deprecated-plugin-migration skill: {_SKILL_MD}")
    return _SKILL_MD.read_text(encoding="utf-8")


def test_deprecated_plugin_migration_file_exists() -> None:
    assert _SKILL_MD.is_file(), f"File does not exist: {_SKILL_MD}"


def test_deprecated_plugin_migration_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"deprecated-plugin-migration SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_deprecated_plugin_migration_contains_phase_markers(skill_text: str) -> None:
    missing = [p for p in _PHASE_MARKERS if p not in skill_text]
    assert not missing, f"deprecated-plugin-migration SKILL.md is missing phase markers: {missing}"


def test_deprecated_plugin_migration_contains_section_markers(skill_text: str) -> None:
    missing = [s for s in _SECTION_MARKERS if s not in skill_text]
    assert not missing, f"deprecated-plugin-migration SKILL.md is missing section markers: {missing}"
