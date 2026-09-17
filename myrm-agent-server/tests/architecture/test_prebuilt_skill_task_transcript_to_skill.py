"""Architecture test for task-transcript-to-skill prebuilt skill asset."""

from __future__ import annotations

from pathlib import Path

import yaml

_SERVER_ROOT = Path(__file__).resolve().parents[2]
SKILL_PATH = _SERVER_ROOT / "assets" / "prebuilt_skills" / "task-transcript-to-skill" / "SKILL.md"


def test_task_transcript_to_skill_asset_structure() -> None:
    assert SKILL_PATH.exists(), f"Skill file does not exist at {SKILL_PATH}"

    raw_text = SKILL_PATH.read_text(encoding="utf-8")
    parts = raw_text.split("---", 2)
    assert len(parts) >= 3, "Skill file must contain YAML frontmatter delimited by ---"

    frontmatter = yaml.safe_load(parts[1])
    assert frontmatter["name"] == "task-transcript-to-skill"
    assert "description" in frontmatter and len(frontmatter["description"]) > 10
    assert frontmatter["version"] == "1.0.0"
    assert frontmatter["category"] in ("productivity", "automation")
    assert "allowed-tools" in frontmatter
    assert "file_write_tool" in frontmatter["allowed-tools"]

    body = parts[2]
    # Check 4 phases exist
    assert "Phase 1: Physical Verification Gate" in body
    assert "Phase 2: Trajectory De-Noising & Flow Mining" in body
    assert "Phase 3: Variable Generalization & Frontmatter Generation" in body
    assert "Phase 4: Cron Blueprint Pairing" in body

    # Check Cron handoff & parameterization
    assert "skill_ids:" in body
    assert "CronBlueprint" in body
