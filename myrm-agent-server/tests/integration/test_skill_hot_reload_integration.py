"""Integration test for skill hot reload functionality."""

import pytest
from myrm_agent_harness.backends.skills.snapshot import SQLiteSkillSnapshot


@pytest.mark.asyncio
async def test_skill_hot_reload_via_api(tmp_path):
    """Test end-to-end hot reload when skills are created/modified/deleted via API."""
    # Create a temporary skills directory
    skills_dir = tmp_path / "test_skills"
    skills_dir.mkdir()

    snapshot_path = skills_dir / ".skills_snapshot.sqlite"
    snapshot = SQLiteSkillSnapshot(snapshot_path)

    # Test 1: Create a skill file directly (simulating external editor)
    skill1_dir = skills_dir / "test-skill-1"
    skill1_dir.mkdir()
    skill1_md = skill1_dir / "SKILL.md"
    skill1_md.write_text(
        """---
description: Test skill for hot reload
version: 1.0.0
---
# Test Skill

This is a test skill for hot reload functionality.
""",
        encoding="utf-8",
    )

    # Trigger sync (simulating what the watcher would do)
    snapshot.sync_all(skills_dir, max_depth=1)

    # Verify skill was added to snapshot
    skills = snapshot.read_all()
    assert len(skills) == 1
    assert skills[0].name == "test-skill-1"
    assert skills[0].description == "Test skill for hot reload"

    # Test 2: Modify the skill
    skill1_md.write_text(
        """---
description: Test skill for hot reload (updated)
version: 1.0.1
---
# Test Skill Updated

This skill has been updated.
""",
        encoding="utf-8",
    )

    # Trigger sync
    snapshot.sync_all(skills_dir, max_depth=1)

    # Verify skill was updated
    skills = snapshot.read_all()
    assert len(skills) == 1
    assert skills[0].description == "Test skill for hot reload (updated)"
    assert skills[0].version == "1.0.1"

    # Test 3: Add another skill
    skill2_dir = skills_dir / "test-skill-2"
    skill2_dir.mkdir()
    skill2_md = skill2_dir / "SKILL.md"
    skill2_md.write_text(
        """---
description: Second test skill
version: 2.0.0
---
# Second Test Skill
""",
        encoding="utf-8",
    )

    # Trigger sync
    snapshot.sync_all(skills_dir, max_depth=1)

    # Verify both skills exist
    skills = snapshot.read_all()
    assert len(skills) == 2
    skill_names = {s.name for s in skills}
    assert skill_names == {"test-skill-1", "test-skill-2"}

    # Test 4: Delete a skill
    import shutil

    shutil.rmtree(skill1_dir)

    # Trigger sync
    snapshot.sync_all(skills_dir, max_depth=1)

    # Verify only one skill remains
    skills = snapshot.read_all()
    assert len(skills) == 1
    assert skills[0].name == "test-skill-2"


@pytest.mark.asyncio
async def test_skill_snapshot_upsert_via_api(tmp_path):
    """Test that API-driven skill operations update the snapshot."""
    skills_dir = tmp_path / "test_skills"
    skills_dir.mkdir()

    snapshot_path = skills_dir / ".skills_snapshot.sqlite"
    snapshot = SQLiteSkillSnapshot(snapshot_path)

    # Create a skill
    skill_dir = skills_dir / "api-skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text(
        """---
description: Skill created via API
version: 1.0.0
---
# API Skill
""",
        encoding="utf-8",
    )

    # Simulate API-driven upsert (what happens in creation/service.py)
    result = snapshot.upsert_from_path(skill_md, workspace_root=skills_dir)
    assert result is True

    # Verify snapshot was updated
    skills = snapshot.read_all()
    assert len(skills) == 1
    assert skills[0].name == "api-skill"

    # Simulate API-driven delete (what happens in creation/service.py)
    result = snapshot.delete_from_path(skill_md)
    assert result is True

    # Verify snapshot was updated
    skills = snapshot.read_all()
    assert len(skills) == 0
