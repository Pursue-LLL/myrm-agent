"""Architecture guard: plugin-syntax-migrator skill must preserve its core operating contract.

[INPUT]
- assets/prebuilt_skills/plugin-syntax-migrator/SKILL.md

[OUTPUT]
- Architecture tests ensuring plugin-syntax-migrator skill retains its 4-phase migration SOP,
  atomic backup guarantee, deprecation fingerprint scanning, and doctor auto-fix validation rules.

[POS]
Architecture test verifying the operational integrity and contract stability of the plugin-syntax-migrator prebuilt skill.
"""

from __future__ import annotations

from pathlib import Path
import pytest
import yaml

_SKILL_MD = (
    Path(__file__).resolve().parents[2]
    / "assets"
    / "prebuilt_skills"
    / "plugin-syntax-migrator"
    / "SKILL.md"
)

_CORE_MODULE_MARKERS = (
    "plugin-syntax-migrator",
    "Zero-Downtime Migration Philosophy",
    "Never Break Without Backup",
    "Deterministic Transpilation",
    "Atomic Verification",
)

_SOP_PHASE_MARKERS = (
    "Phase 1: Deprecation Fingerprint Scanning",
    "Phase 2: Diff Matrix & Risk Assessment",
    "Phase 3: Atomic In-Place Patching & Backup",
    "Phase 4: Post-Fix Validation & Doctor Check",
)

_CONTRACT_MARKERS = (
    # Tool definitions
    "file_read_tool",
    "file_write_tool",
    "file_edit_tool",
    "grep_tool",
    # Verification steps
    "deprecation_fingerprint_scanned",
    "preflight_backup_created",
    "in_place_fix_validated",
    "doctor_health_check_passed",
    # Deprecation patterns
    "primaryEnv",
    "required_oauth_issuers",
    "bash_code_execute_tool",
)

_MAX_SKILL_CHARS = 12_000


def test_plugin_syntax_migrator_skill_exists_and_readable() -> None:
    """The prebuilt skill must exist on disk and be non-empty."""
    assert _SKILL_MD.is_file(), f"Expected skill file at {_SKILL_MD}"
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert len(content.strip()) > 0, "SKILL.md must not be empty"


def test_plugin_syntax_migrator_skill_has_valid_frontmatter() -> None:
    """Must have valid YAML frontmatter with required contract fields."""
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert content.startswith("---"), "SKILL.md must start with YAML frontmatter delimiter"
    parts = content.split("---", 2)
    assert len(parts) >= 3, "SKILL.md must contain frontmatter closing delimiter"
    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "plugin-syntax-migrator"
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] == "engineering"
    assert "tools" in frontmatter
    assert "verification_steps" in frontmatter
    assert len(frontmatter["verification_steps"]) >= 4


def test_plugin_syntax_migrator_skill_contains_core_architecture_markers() -> None:
    """Must contain all foundational migration philosophy concepts."""
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CORE_MODULE_MARKERS:
        assert marker in content, f"Missing architectural marker: {marker}"


def test_plugin_syntax_migrator_skill_retains_four_phase_sop() -> None:
    """Must retain the complete 4-phase migration SOP."""
    content = _SKILL_MD.read_text(encoding="utf-8")
    for phase in _SOP_PHASE_MARKERS:
        assert phase in content, f"Missing SOP phase marker: {phase}"


def test_plugin_syntax_migrator_skill_retains_contract_markers() -> None:
    """Must retain all key contract markers, tools, deprecation patterns, and verification steps."""
    content = _SKILL_MD.read_text(encoding="utf-8")
    for marker in _CONTRACT_MARKERS:
        assert marker in content, f"Missing contract marker: {marker}"


def test_plugin_syntax_migrator_skill_fits_context_budget() -> None:
    """Skill must stay within budget to ensure high-efficiency agent loading."""
    content = _SKILL_MD.read_text(encoding="utf-8")
    assert len(content) <= _MAX_SKILL_CHARS, (
        f"SKILL.md length ({len(content)}) exceeds maximum budget ({_MAX_SKILL_CHARS})"
    )
