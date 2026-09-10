"""Architecture test for deprecated-skill-doctor-fix prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path

import yaml

SKILL_PATH = Path("assets/prebuilt_skills/deprecated-skill-doctor-fix/SKILL.md")


def test_deprecated_skill_doctor_fix_asset_structure() -> None:
    assert SKILL_PATH.exists(), f"Skill file does not exist at {SKILL_PATH}"

    raw_text = SKILL_PATH.read_text(encoding="utf-8")
    parts = raw_text.split("---", 2)
    assert len(parts) >= 3, "Skill file must contain YAML frontmatter delimited by ---"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "deprecated-skill-doctor-fix"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] == "engineering"
    assert "allowed-tools" in frontmatter

    body = parts[2]
    # Check 4 stages exist
    assert "Stage 1: Multi-Point Deprecation Audit" in body
    assert "Stage 2: Risk-Tiered Diagnosis Report" in body
    assert "Stage 3: Non-Destructive In-Place Auto-Fix" in body
    assert "Stage 4: Post-Fix Validation & Health Gate" in body

    # Check key mappings and diagnostics
    assert "allowed-tools" in body
    assert "bash_code_execute_tool" in body
    assert "Skill Doctor Diagnosis Report" in body
