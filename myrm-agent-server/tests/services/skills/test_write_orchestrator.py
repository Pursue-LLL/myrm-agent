"""SkillMd write orchestrator: DB/disk ordering."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.api.skills import compute_content_hash


@pytest.mark.asyncio
async def test_orchestrate_skill_md_uses_sync_disk_without_prior_raw_write() -> None:
    from app.services.skills.write_orchestrator import orchestrate_skill_file_write

    skill_id = "skill-test-1"
    content = "---\nname: demo\ndescription: d\n---\n# Body\n"
    content_hash = compute_content_hash(content)

    with (
        patch(
            "app.services.skills.write_orchestrator._read_current_text",
            new_callable=AsyncMock,
            return_value="---\nname: demo\ndescription: old\n---\n# Old\n",
        ),
        patch(
            "app.services.skills.write_orchestrator.persist_skill_md_snapshot",
            new_callable=AsyncMock,
            return_value=(True, 2),
        ) as mock_persist,
        patch(
            "app.core.skills.store.service.skills_service.update_skill_file",
            new_callable=AsyncMock,
        ) as mock_update,
    ):
        result = await orchestrate_skill_file_write(
            skill_id,
            "SKILL.md",
            content,
            created_by="test",
        )

    mock_persist.assert_awaited_once()
    _args, kwargs = mock_persist.await_args
    assert kwargs.get("sync_disk") is True
    mock_update.assert_not_awaited()
    assert result.version_persisted is True
    assert result.version_number == 2
    assert result.content_hash == content_hash
