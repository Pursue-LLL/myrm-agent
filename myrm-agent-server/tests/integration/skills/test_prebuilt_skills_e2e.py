"""End-to-end integration tests for prebuilt skill pipeline (no mocks on storage/sync).

Validates: seed sync → metadata discovery → user enablement → get_skills_by_ids
for BuiltIn Agent default bindings.
Also validates: reset-to-default and accept-upstream API logic.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from myrm_agent_harness.agent.skills.discovery.sanitizer import SKILL_MD_FILE
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend
from myrm_agent_harness.toolkits.storage.paths import (
    get_skill_file_path,
    get_skill_metadata_path,
)
from myrm_agent_harness.toolkits.storage.types import SkillType

from app.core.skills import prebuilt_sync
from app.core.skills.store.service import SkillsService
from app.core.skills.store.user_config import UserSkillConfigManager
from app.services.agent.builtin_initializer import _BUILTIN_AGENTS


@pytest.fixture
def storage(tmp_path: Path) -> LocalStorageBackend:
    return LocalStorageBackend(str(tmp_path))


@pytest.fixture(autouse=True)
def reset_sync_flag() -> None:
    prebuilt_sync._synced = False  # noqa: SLF001
    yield
    prebuilt_sync._synced = False  # noqa: SLF001


@pytest.fixture
def skills_service(storage: LocalStorageBackend) -> SkillsService:
    service = SkillsService(storage=storage)
    return service


@pytest.mark.asyncio
async def test_prebuilt_pipeline_lists_all_seeds(
    skills_service: SkillsService,
) -> None:
    """Full pipeline: sync seeds → list_prebuilt discovers all via metadata."""
    sync_result = await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)
    assert len(sync_result.skill_ids) >= 12

    await skills_service.user_config.ensure_prebuilt_enabled_after_sync(list(sync_result.skill_ids))

    listed = await skills_service.list_skills()
    prebuilt_ids = {s.id for s in listed if s.type.value == "prebuilt"}
    assert "systematic-debugging" in prebuilt_ids
    assert "code-review" in prebuilt_ids
    assert "test-driven-development" in prebuilt_ids


@pytest.mark.asyncio
async def test_builtin_developer_default_skills_resolvable(
    skills_service: SkillsService,
) -> None:
    """BuiltIn developer default_skill_ids resolve via get_skills_by_ids."""
    dev_spec = next(s for s in _BUILTIN_AGENTS if s.id == "builtin-developer")
    assert dev_spec.default_skill_ids

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    resolved = await skills_service.get_skills_by_ids(list(dev_spec.default_skill_ids))
    resolved_ids = {s.id for s in resolved}

    assert resolved_ids == set(dev_spec.default_skill_ids)
    for skill in resolved:
        assert skill.description
        assert skill.storage_path


@pytest.mark.asyncio
async def test_disable_prebuilt_persists_and_blocks_re_enable(
    storage: LocalStorageBackend,
) -> None:
    """Disable records disabled_prebuilt_ids; sync does not re-enable."""
    manager = UserSkillConfigManager(storage)
    result = await prebuilt_sync.sync_prebuilt_seeds(storage)

    await manager.enable_prebuilt_skill("systematic-debugging")
    await manager.disable_prebuilt_skill("systematic-debugging")

    config = await manager.get_config()
    assert "systematic-debugging" not in config.enabled_prebuilt_ids
    assert "systematic-debugging" in config.disabled_prebuilt_ids

    await manager.ensure_prebuilt_enabled_after_sync(list(result.skill_ids))
    config_after = await manager.get_config()
    assert "systematic-debugging" not in config_after.enabled_prebuilt_ids


@pytest.mark.asyncio
async def test_create_skill_backend_loads_prebuilt(
    storage: LocalStorageBackend,
) -> None:
    """loader.create_skill_backend assembles prebuilt backend after sync."""
    from app.core.skills.loader import create_skill_backend

    service = SkillsService(storage=storage)
    with patch("app.core.skills.store.service.skills_service", service):
        backend = await create_skill_backend(storage=storage)

    skills = await backend.list_skills()
    names = {s.name for s in skills}
    assert "systematic-debugging" in names


# --- Prebuilt update management (reset-to-default / accept-upstream) ---


@pytest.mark.asyncio
async def test_reset_to_default_restores_bundled_content(
    skills_service: SkillsService,
) -> None:
    """reset_prebuilt_to_default restores original bundled content and clears flags."""
    from app.api.skills.prebuilt import _apply_bundled_source, _get_prebuilt_skill

    storage = skills_service.storage
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    skill_id = "code-review"
    md_path = get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    original_md = await storage.read_text(md_path)
    original_meta = json.loads(await storage.read_text(meta_path))
    original_hash = original_meta["origin_hash"]

    user_content = "# My Overridden Code Review\nCustom content here."
    await storage.write_text(md_path, user_content)
    original_meta["has_upstream_update"] = True
    await storage.write_text(meta_path, json.dumps(original_meta, indent=2))

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        skill = await _get_prebuilt_skill(skill_id)
        assert skill.has_upstream_update is True

        await _apply_bundled_source(skill, skill_id)

    restored_md = await storage.read_text(md_path)
    restored_meta = json.loads(await storage.read_text(meta_path))

    assert restored_md == original_md
    assert restored_meta["has_upstream_update"] is False
    assert restored_meta["origin_hash"] == original_hash


@pytest.mark.asyncio
async def test_accept_upstream_clears_flag(
    skills_service: SkillsService,
) -> None:
    """accept_prebuilt_upstream applies bundled source and clears has_upstream_update."""
    from app.api.skills.prebuilt import _apply_bundled_source, _get_prebuilt_skill

    storage = skills_service.storage
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    skill_id = "code-review"
    get_skill_file_path(SkillType.PREBUILT, skill_id, SKILL_MD_FILE)
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)

    meta = json.loads(await storage.read_text(meta_path))
    meta["has_upstream_update"] = True
    await storage.write_text(meta_path, json.dumps(meta, indent=2))

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        skill = await _get_prebuilt_skill(skill_id)
        assert skill.has_upstream_update is True

        await _apply_bundled_source(skill, skill_id)

    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta["has_upstream_update"] is False
    assert new_meta["origin_hash"] is not None


@pytest.mark.asyncio
async def test_get_prebuilt_skill_404_for_nonexistent(
    skills_service: SkillsService,
) -> None:
    """_get_prebuilt_skill raises 404 for non-existent skill."""
    from app.api.skills.prebuilt import _get_prebuilt_skill

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        with pytest.raises(HTTPException) as exc_info:
            await _get_prebuilt_skill("nonexistent-skill-xyz")
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_apply_bundled_source_404_for_missing_seed(
    skills_service: SkillsService,
) -> None:
    """_apply_bundled_source raises 404 when bundled seed directory is missing."""
    from app.api.skills.prebuilt import _apply_bundled_source
    from app.core.skills.models import Skill

    fake_skill = Skill(
        id="fake-missing-seed",
        type=SkillType.PREBUILT,
        name="fake-missing-seed",
        description="test",
        storage_path="skills/prebuilt/fake-missing-seed",
    )

    with pytest.raises(HTTPException) as exc_info:
        await _apply_bundled_source(fake_skill, "fake-missing-seed")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_reset_to_default_endpoint_returns_ok(
    skills_service: SkillsService,
) -> None:
    """reset_prebuilt_to_default endpoint returns proper status and message."""
    from app.api.skills.prebuilt import reset_prebuilt_to_default

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        result = await reset_prebuilt_to_default("code-review")

    assert result["status"] == "ok"
    assert "code-review" in result["message"]


@pytest.mark.asyncio
async def test_accept_upstream_endpoint_rejects_no_pending(
    skills_service: SkillsService,
) -> None:
    """accept_prebuilt_upstream rejects when has_upstream_update is False."""
    from app.api.skills.prebuilt import accept_prebuilt_upstream

    await prebuilt_sync.sync_prebuilt_seeds(skills_service.storage)

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        with pytest.raises(HTTPException) as exc_info:
            await accept_prebuilt_upstream("code-review")
        assert exc_info.value.status_code == 400
        assert "No upstream update pending" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_accept_upstream_endpoint_succeeds_with_pending(
    skills_service: SkillsService,
) -> None:
    """accept_prebuilt_upstream succeeds when has_upstream_update is True."""
    from app.api.skills.prebuilt import accept_prebuilt_upstream

    storage = skills_service.storage
    await prebuilt_sync.sync_prebuilt_seeds(storage)

    skill_id = "code-review"
    meta_path = get_skill_metadata_path(SkillType.PREBUILT, skill_id)
    meta = json.loads(await storage.read_text(meta_path))
    meta["has_upstream_update"] = True
    await storage.write_text(meta_path, json.dumps(meta, indent=2))

    with patch("app.api.skills.prebuilt.skills_service", skills_service):
        result = await accept_prebuilt_upstream(skill_id)

    assert result["status"] == "ok"
    assert skill_id in result["message"]

    new_meta = json.loads(await storage.read_text(meta_path))
    assert new_meta["has_upstream_update"] is False
