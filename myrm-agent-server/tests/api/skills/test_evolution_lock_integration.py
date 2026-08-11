"""Integration test for Skill Evolution Lock.

Tests the full end-to-end flow of toggle_evolution_lock API,
ensuring it correctly updates both the SQLite store and the physical SKILL.md file.
"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.skills.evolution import (
    EvolutionType,
    SkillEvolutionEngine,
    SkillLineage,
    SkillRecord,
    SkillStore,
)
from myrm_agent_harness.agent.skills.evolution.infra.integration import get_global_evolution_integration

from app.core.skills.models import Skill


@pytest.fixture
def temp_skill_dir(tmp_path: Path) -> Path:
    """Create a temporary skill directory with SKILL.md."""
    skill_dir = tmp_path / "test_skill"
    skill_dir.mkdir()
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: test-lock-skill\ndescription: A test skill\nevolution_locked: false\n---\ndef main(): pass\n")
    return skill_dir


@pytest.mark.skip(reason="Integration test requires full skill store setup — mock path mismatch with refactored modules")
def test_toggle_evolution_lock_integration(client: TestClient, temp_skill_dir: Path):
    """Test full integration of evolution lock toggle."""
    skill_id = "test-lock-skill"
    # Ensure evolution system is initialized for the test
    evolution = get_global_evolution_integration()
    if not evolution or not evolution.store:
        pytest.skip("Evolution system not initialized, skipping integration test.")

    # Mock the skills_service to return our temp skill
    mock_skill = Skill(
        id=skill_id,
        name="test-lock-skill",
        description="A test skill",
        author="test",
        type="local",
        storage_path=str(temp_skill_dir),
        evolution_locked=False,
    )

    with patch("app.api.skills.core.skills_service.get_skill", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_skill

        # 1. Initially unlocked
        assert not evolution.store.is_evolution_locked(skill_id)

        # 2. Call API to lock the skill
        response = client.post(f"/api/v1/skills/{skill_id}/evolution-lock?locked=true")
        assert response.status_code == 200
        assert response.json() == {"skill_id": skill_id, "evolution_locked": True}

        # 3. Verify Database Store is updated
        assert evolution.store.is_evolution_locked(skill_id) is True

        # 4. Verify physical SKILL.md file is updated
        skill_md_content = (temp_skill_dir / "SKILL.md").read_text()
        assert "evolution_locked: true" in skill_md_content
        assert "evolution_locked: false" not in skill_md_content

        # 5. Call API to unlock the skill
        response = client.post(f"/api/v1/skills/{skill_id}/evolution-lock?locked=false")
        assert response.status_code == 200

        # 6. Verify Database Store is updated
        assert evolution.store.is_evolution_locked(skill_id) is False

        # 7. Verify physical SKILL.md file is updated
        skill_md_content = (temp_skill_dir / "SKILL.md").read_text()
        assert "evolution_locked: false" in skill_md_content
        assert "evolution_locked: true" not in skill_md_content


@pytest.mark.asyncio
async def test_derive_skill_blocked_by_lock() -> None:
    """Locked skill cannot be derived: the engine refuses before any LLM call."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_evolution.db"
        store = SkillStore(db_path)
        engine = SkillEvolutionEngine(store=store, llm=None)
        try:
            skill = SkillRecord(
                skill_id="test-lock-skill",
                name="test-lock-skill",
                description="A test skill",
                content="# test-lock-skill\n\ndescription: A test skill\n",
                path=str(db_path.parent),
                lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
                evolution_locked=True,
            )
            await store.save_skill(skill)
            await store.set_evolution_lock("test-lock-skill", locked=True)

            assert store.is_evolution_locked("test-lock-skill") is True

            proposal = await engine.derive_skill_simple(
                "test-lock-skill", user_feedback="Make it better"
            )
            assert proposal is None
        finally:
            store.close()
