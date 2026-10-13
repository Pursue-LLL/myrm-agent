"""Architecture guard: deprecated-plugin-migration-doctor skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/deprecated-plugin-migration-doctor/SKILL.md
- myrm-agent/myrm-agent-server/assets/prebuilt_skills/deprecated-plugin-migration-doctor/SKILL.md

[OUTPUT]
- Architecture tests ensuring deprecated-plugin-migration-doctor retains 4-phase pipeline,
  rule transformation table, and atomic backup rollback protocol, and that the hook it
  migrates a legacy declaration to is one the runtime hook parser registers.

[POS]
Architecture test verifying the operational integrity and contract stability of the
deprecated-plugin-migration-doctor prebuilt skill.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from myrm_agent_harness.agent.hooks import CommandHookDefinition, HookEvent, parse_hooks_from_skill_md

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_WORKSPACE_ROOT = Path(__file__).resolve().parents[4]

_SERVER_SKILL_MD = _SERVER_ROOT / "assets" / "prebuilt_skills" / "deprecated-plugin-migration-doctor" / "SKILL.md"

_WORKSPACE_SKILL_MD = _WORKSPACE_ROOT / "assets" / "prebuilt_skills" / "deprecated-plugin-migration-doctor" / "SKILL.md"

_FOUR_PHASES = (
    "Phase 1: Lint & Deprecation Probe",
    "Phase 2: Diff & Impact Analysis",
    "Phase 3: Atomic Backup & Fix",
    "Phase 4: Validation & Rollback Gate",
)

_CONTRACT_MARKERS = (
    "deprecated-plugin-migration-doctor",
    "openclaw doctor --fix",
    ".doctor_backup",
    "Deprecation Rule Registry",
    "Atomic Rollback Protocol",
)

_MAX_SKILL_CHARS = 12_000

_HOOK_MIGRATION_ROW = re.compile(r"`on_agent_init: run\.py` \| `(hooks: .+?)` \|")


@pytest.fixture(scope="module")
def skill_text() -> str:
    path = _SERVER_SKILL_MD if _SERVER_SKILL_MD.is_file() else _WORKSPACE_SKILL_MD
    if not path.is_file():
        pytest.fail(f"Missing deprecated-plugin-migration-doctor skill at {path}")
    return path.read_text(encoding="utf-8")


def test_deprecated_plugin_migration_doctor_file_exists() -> None:
    assert _SERVER_SKILL_MD.is_file() or _WORKSPACE_SKILL_MD.is_file(), (
        f"File does not exist: {_SERVER_SKILL_MD} nor {_WORKSPACE_SKILL_MD}"
    )


def test_deprecated_plugin_migration_doctor_char_limit(skill_text: str) -> None:
    assert len(skill_text) <= _MAX_SKILL_CHARS, (
        f"deprecated-plugin-migration-doctor SKILL.md is {len(skill_text)} chars, exceeding {_MAX_SKILL_CHARS}"
    )


def test_deprecated_plugin_migration_doctor_contains_all_phases(skill_text: str) -> None:
    missing = [phase for phase in _FOUR_PHASES if phase not in skill_text]
    assert not missing, f"deprecated-plugin-migration-doctor SKILL.md is missing phases: {missing}"


def test_deprecated_plugin_migration_doctor_contains_contract_markers(skill_text: str) -> None:
    missing = [marker for marker in _CONTRACT_MARKERS if marker not in skill_text]
    assert not missing, f"deprecated-plugin-migration-doctor SKILL.md is missing contract markers: {missing}"


def test_deprecated_plugin_migration_doctor_hook_row_is_registered_by_the_hook_parser(skill_text: str) -> None:
    """The model copies this row into migrated skills, so the runtime must register what it declares."""
    row = _HOOK_MIGRATION_ROW.search(skill_text)
    assert row, "deprecated-plugin-migration-doctor SKILL.md has no on_agent_init -> hooks migration row"

    hooks, _ = parse_hooks_from_skill_md(f"---\nname: migrated\n{row.group(1)}\n---\n")

    assert len(hooks) == 1, f"the declaration {row.group(1)!r} registers {len(hooks)} hooks, expected 1"
    event, definition = hooks[0]
    assert event is HookEvent.SESSION_START
    assert isinstance(definition, CommandHookDefinition)
    assert definition.command == "run.py"
