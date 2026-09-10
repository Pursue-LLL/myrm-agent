"""Architecture test for task-transcript-to-skill prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path
import yaml

SKILL_PATH = Path("assets/prebuilt_skills/task-transcript-to-skill/SKILL.md")


def test_task_transcript_to_skill_asset_structure() -> None:
    assert SKILL_PATH.exists(), f"Skill file does not exist at {SKILL_PATH}"

    raw_text = SKILL_PATH.read_text(encoding="utf-8")
    parts = raw_text.split("---", 2)
    assert len(parts) >= 3, "Skill file must contain YAML frontmatter delimited by ---"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "task-transcript-to-skill"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] == "productivity"
    assert "allowed-tools" in frontmatter
    assert "skill_manage_tool" in frontmatter["allowed-tools"]

    body = parts[2]
    # Check 4 phases exist
    assert "Phase 1: Generalization & Slot Extraction" in body
    assert "Phase 2: Standardized Procedural Schema" in body
    assert "Phase 3: Packaging & Validation" in body
    assert "Phase 4: Save & Cron Automation Handoff" in body

    # Check Cron handoff & parameterization
    assert "cron_expression" in body
    assert "${TARGET_DIR}" in body or "${DATE}" in body
