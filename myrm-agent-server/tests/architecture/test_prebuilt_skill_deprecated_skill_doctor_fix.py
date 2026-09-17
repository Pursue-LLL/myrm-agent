"""Architecture test for deprecated-skill-doctor-fix prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path

import yaml

_SERVER_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = _SERVER_ROOT / "assets" / "prebuilt_skills" / "plugin-syntax-migrator-doctor" / "SKILL.md"


def test_deprecated_skill_doctor_fix_asset_structure() -> None:
    assert SKILL_PATH.exists(), f"Skill file does not exist at {SKILL_PATH}"

    raw_text = SKILL_PATH.read_text(encoding="utf-8")
    parts = raw_text.split("---", 2)
    assert len(parts) >= 3, "Skill file must contain YAML frontmatter delimited by ---"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "plugin-syntax-migrator-doctor"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] == "engineering"
    assert "allowed-tools" in frontmatter

    body = parts[2]
    # Check 4 stages exist
    assert "Stage 1: Syntax & Legacy Schema Scanning" in body
    assert "Stage 2: Deprecation Rules Engine" in body
    assert "Stage 3: Safety Backup & Diff Preview" in body
    assert "Stage 4: Idempotent Patching & Schema Validation" in body

    # Check key mappings and diagnostics
    assert "allowed-tools" in body
    assert "Doctor Fix Report" in body
